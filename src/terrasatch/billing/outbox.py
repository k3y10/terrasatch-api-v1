"""Transactional email outbox with bounded idempotent retries."""

from dataclasses import asdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from terrasatch.billing.models import BillingActivation, BillingEmailOutbox
from terrasatch.billing.notifications import BillingEmailContext, deliver_billing_email
from terrasatch.billing.service import _token_hash, recover_activation_token
from terrasatch.database.session import create_session_factory
from terrasatch.errors import ProviderUnavailable


async def enqueue_email(session, *, event_id, kind, context, activation_token=None):
    values = asdict(context)
    for key, value in values.items():
        if isinstance(value, datetime):
            values[key] = value.isoformat()
    activation_id = None
    if activation_token:
        activation_id = await session.scalar(
            select(BillingActivation.id).where(
                BillingActivation.token_hash == _token_hash(activation_token)
            )
        )
        if activation_id is None:
            raise ValueError("Activation intent missing")
    session.add(
        BillingEmailOutbox(
            event_id=event_id,
            kind=kind,
            context=values,
            activation_id=activation_id,
            next_attempt_at=datetime.now(UTC),
        )
    )
    await session.flush()


async def dispatch_email_batch(settings, *, session_factory=None, limit=20):
    """Read only committed intents. Competing PostgreSQL workers skip locked rows.

    Retry ambiguous sends using the identical event ID and payload. Stop before
    Resend's 24-hour deduplication window expires; operators reconcile those rows.
    """
    factory = session_factory or create_session_factory(settings)
    sent = 0
    for _ in range(limit):
        # Persist a lease and first-attempt timestamp before any external send.
        async with factory() as session:
            async with session.begin():
                now = datetime.now(UTC)
                row = await session.scalar(
                    select(BillingEmailOutbox)
                    .where(
                        BillingEmailOutbox.sent_at.is_(None),
                        BillingEmailOutbox.next_attempt_at <= now,
                        BillingEmailOutbox.last_error.is_distinct_from("reconcile_required"),
                        BillingEmailOutbox.last_error.is_distinct_from("activation_expired"),
                        BillingEmailOutbox.last_error.is_distinct_from("activation_consumed"),
                    )
                    .order_by(BillingEmailOutbox.next_attempt_at)
                    .with_for_update(skip_locked=True)
                    .limit(1)
                )
                if row is None:
                    break
                first = row.first_attempt_at
                if first and now - first.replace(tzinfo=UTC) >= timedelta(hours=23):
                    row.last_error = "reconcile_required"
                    continue
                row.first_attempt_at = first or now
                row.attempts += 1
                row.next_attempt_at = now + timedelta(minutes=2)
                event_id = row.event_id
            # The lease/attempt timestamp has committed before delivery starts.
        async with factory() as session:
            async with session.begin():
                row = await session.get(BillingEmailOutbox, event_id, with_for_update=True)
                if row.sent_at is not None:
                    continue
                if row.activation_id:
                    activation = await session.get(
                        BillingActivation, row.activation_id, with_for_update=True
                    )
                    if activation is None:
                        row.last_error = "reconcile_required"
                        continue
                    if activation.consumed_at is not None:
                        row.last_error = "activation_consumed"
                        continue
                    if activation.expires_at.replace(tzinfo=UTC) <= datetime.now(UTC):
                        # A fresh activation needs a new explicit intent and idempotency key.
                        # Never replace this retry's payload under an existing provider key.
                        row.last_error = "activation_expired"
                        continue
                values = dict(row.context)
                for key in ("trial_ends_at", "current_period_end", "grace_ends_at"):
                    if values[key]:
                        values[key] = datetime.fromisoformat(values[key])
                token = (
                    recover_activation_token(settings, row.activation_id)
                    if row.activation_id
                    else None
                )
                if token and _token_hash(token) != activation.token_hash:
                    row.last_error = "reconcile_required"
                    continue
                try:
                    receipt = await deliver_billing_email(
                        settings=settings,
                        event_id=row.event_id,
                        kind=row.kind,
                        context=BillingEmailContext(**values),
                        activation_token=token,
                    )
                    if receipt is None:
                        raise ProviderUnavailable("Email is not configured")
                except ProviderUnavailable:
                    row.last_error = "delivery_failed"
                    row.next_attempt_at = now + timedelta(
                        seconds=min(3600, 30 * 2 ** min(row.attempts, 7))
                    )
                else:
                    row.sent_at = now
                    row.delivery_provider = receipt.provider
                    row.provider_message_id = receipt.message_id
                    row.delivery_status = "accepted"
                    row.last_error = None
                    sent += 1
    return sent
