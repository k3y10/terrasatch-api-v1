"""Persistent billing state mirrored from Stripe and local onboarding."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from terrasatch.database.base import Base
from terrasatch.database.types import TimestampMixin, UUIDPrimaryKeyMixin


class BillingSignup(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Short-lived self-service signup state created before Stripe Checkout."""

    __tablename__ = "billing_signups"
    __table_args__ = (
        Index("ix_billing_signups_email", "email"),
        Index("ix_billing_signups_status", "status"),
    )

    email: Mapped[str] = mapped_column(String(320), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    organization_name: Mapped[str] = mapped_column(String(255), nullable=False)
    plan_code: Mapped[str] = mapped_column(String(32), nullable=False)
    billing_interval: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    stripe_checkout_session_id: Mapped[str | None] = mapped_column(
        String(255), unique=True, nullable=True
    )
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class BillingCustomer(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Stripe customer identity bound to one TerraSatch organization."""

    __tablename__ = "billing_customers"
    __table_args__ = (
        UniqueConstraint("organization_id", name="uq_billing_customers_organization"),
        UniqueConstraint("stripe_customer_id", name="uq_billing_customers_stripe_customer"),
        Index("ix_billing_customers_account_id", "account_id"),
    )

    account_id: Mapped[UUID] = mapped_column(
        ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False
    )
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    stripe_customer_id: Mapped[str] = mapped_column(String(255), nullable=False)


class Subscription(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Current subscription state used for TerraSatch service authorization."""

    __tablename__ = "subscriptions"
    __table_args__ = (
        UniqueConstraint("organization_id", name="uq_subscriptions_organization"),
        UniqueConstraint("billing_customer_id", name="uq_subscriptions_billing_customer"),
        UniqueConstraint("stripe_subscription_id", name="uq_subscriptions_stripe_subscription"),
        Index("ix_subscriptions_status", "status"),
    )

    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    billing_customer_id: Mapped[UUID] = mapped_column(
        ForeignKey("billing_customers.id", ondelete="RESTRICT"), nullable=False
    )
    stripe_subscription_id: Mapped[str] = mapped_column(String(255), nullable=False)
    stripe_price_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    plan_code: Mapped[str] = mapped_column(String(32), nullable=False)
    billing_interval: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    trial_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_period_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    current_period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    grace_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_invoice_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_payment_failed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class BillingActivation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Single-use password activation token for a newly provisioned owner."""

    __tablename__ = "billing_activations"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_billing_activations_token_hash"),
        Index("ix_billing_activations_user_id", "user_id"),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class StripeEvent(TimestampMixin, Base):
    """Idempotency ledger for verified Stripe webhook events."""

    __tablename__ = "stripe_events"

    event_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(255), nullable=False)
    livemode: Mapped[bool] = mapped_column(Boolean, nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class BillingEmailOutbox(TimestampMixin, Base):
    """Commit-safe email intent. No plaintext activation credentials are stored."""

    __tablename__ = "billing_email_outbox"
    event_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    context: Mapped[dict] = mapped_column(JSON, nullable=False)
    activation_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("billing_activations.id", ondelete="RESTRICT"), nullable=True
    )
    password_reset_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("password_reset_intents.id", ondelete="RESTRICT"), nullable=True
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    first_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivery_provider: Mapped[str | None] = mapped_column(String(64))
    provider_message_id: Mapped[str | None] = mapped_column(String(255))
    delivery_status: Mapped[str | None] = mapped_column(String(64))
    provider_event_id: Mapped[str | None] = mapped_column(String(255))
    provider_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(100))
