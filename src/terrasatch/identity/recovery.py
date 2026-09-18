"""Single-use TerraSatch browser-account recovery primitives."""

from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.admin.security import hash_admin_password
from terrasatch.config import Settings
from terrasatch.errors import InvalidConfiguration, ResourceNotFound
from terrasatch.identity.models import Membership, Organization, PasswordResetIntent, User


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def recover_password_reset_token(settings: Settings, reset_id: UUID) -> str:
    """Deterministically recover a purpose-bound reset token for durable email retries."""

    secret = settings.billing_activation_signing_secret
    if secret is None:
        raise InvalidConfiguration("Account recovery signing secret is not configured")
    return hmac.new(
        secret.get_secret_value().encode(),
        f"terrasatch-password-reset-v1:{reset_id}".encode(),
        hashlib.sha256,
    ).hexdigest()


async def create_password_reset_intent(
    session: AsyncSession,
    *,
    email: str,
    settings: Settings,
) -> PasswordResetIntent | None:
    """Create one reset intent without disclosing whether the account exists."""

    normalized = email.strip().casefold()
    user = await session.scalar(
        select(User).where(User.email == normalized, User.enabled.is_(True))
    )
    if user is None or not user.password_hash:
        return None

    membership_id = await session.scalar(
        select(Membership.id)
        .join(Organization, Organization.id == Membership.organization_id)
        .where(
            Membership.user_id == user.id,
            Membership.enabled.is_(True),
            Organization.enabled.is_(True),
        )
        .limit(1)
    )
    if membership_id is None:
        return None

    now = datetime.now(UTC)
    await session.execute(
        update(PasswordResetIntent)
        .where(
            PasswordResetIntent.user_id == user.id,
            PasswordResetIntent.consumed_at.is_(None),
        )
        .values(consumed_at=now)
    )

    reset_id = uuid4()
    token = recover_password_reset_token(settings, reset_id)
    intent = PasswordResetIntent(
        id=reset_id,
        user_id=user.id,
        token_hash=_token_hash(token),
        expires_at=now + timedelta(minutes=settings.account_password_reset_ttl_minutes),
    )
    session.add(intent)
    await session.flush()
    return intent


async def reset_password(
    session: AsyncSession,
    *,
    token: str,
    password: str,
) -> User:
    """Consume one valid reset token and replace the user's browser password."""

    now = datetime.now(UTC)
    intent = await session.scalar(
        select(PasswordResetIntent)
        .where(
            PasswordResetIntent.token_hash == _token_hash(token),
            PasswordResetIntent.consumed_at.is_(None),
            PasswordResetIntent.expires_at > now,
        )
        .with_for_update()
    )
    if intent is None:
        raise ResourceNotFound("Password reset link is invalid, expired, or already used")

    user = await session.get(User, intent.user_id, with_for_update=True)
    if user is None or not user.enabled:
        raise ResourceNotFound("Password reset account was not found")

    try:
        user.password_hash = hash_admin_password(password)
        user.credential_version += 1
    except ValueError as error:
        raise InvalidConfiguration(str(error)) from error

    await session.execute(
        update(PasswordResetIntent)
        .where(
            PasswordResetIntent.user_id == user.id,
            PasswordResetIntent.consumed_at.is_(None),
        )
        .values(consumed_at=now)
    )
    await session.flush()
    return user
