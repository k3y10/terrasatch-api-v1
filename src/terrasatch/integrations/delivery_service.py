"""Idempotent, audited execution of provider output operations."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.config import Settings
from terrasatch.errors import InvalidConfiguration, ProviderUnavailable, TerraSatchError
from terrasatch.identity.models import MembershipRole

from .models import IntegrationDelivery, IntegrationStatus
from .oauth_service import active_credentials
from .operations import create_google_drive_file, send_slack_message
from .service import get_connection_for_management


def delivery_payload(delivery: IntegrationDelivery) -> dict[str, object]:
    return {
        "id": str(delivery.id),
        "connection_id": str(delivery.connection_id),
        "request_id": str(delivery.request_id),
        "operation": delivery.operation,
        "status": delivery.status,
        "external_id": delivery.external_id,
        "response_metadata": dict(delivery.response_metadata or {}),
        "last_error": delivery.last_error,
        "created_at": delivery.created_at,
        "updated_at": delivery.updated_at,
    }


async def prepare_delivery(
    session: AsyncSession,
    *,
    organization_id: UUID,
    user_id: UUID,
    role: MembershipRole,
    connection_id: UUID,
    request_id: UUID,
    operation: str,
    request_metadata: dict[str, object],
) -> tuple[IntegrationDelivery, bool]:
    connection = await get_connection_for_management(
        session,
        organization_id=organization_id,
        user_id=user_id,
        role=role,
        connection_id=connection_id,
    )
    if connection.status != IntegrationStatus.CONNECTED.value:
        raise ProviderUnavailable("Integration must be connected before it can deliver output")
    provider_for_operation = {
        "slack_message": "slack",
        "drive_export": "google_drive",
    }.get(operation)
    if provider_for_operation is None or connection.provider != provider_for_operation:
        raise InvalidConfiguration("Integration does not support this output operation")

    existing = await session.scalar(
        select(IntegrationDelivery).where(
            IntegrationDelivery.organization_id == organization_id,
            IntegrationDelivery.connection_id == connection_id,
            IntegrationDelivery.request_id == request_id,
        )
    )
    if existing is not None:
        return existing, False

    delivery = IntegrationDelivery(
        organization_id=organization_id,
        connection_id=connection_id,
        requested_by_user_id=user_id,
        request_id=request_id,
        operation=operation,
        status="pending",
        request_metadata=dict(request_metadata),
        response_metadata={},
    )
    session.add(delivery)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        existing = await session.scalar(
            select(IntegrationDelivery).where(
                IntegrationDelivery.organization_id == organization_id,
                IntegrationDelivery.connection_id == connection_id,
                IntegrationDelivery.request_id == request_id,
            )
        )
        if existing is None:
            raise
        return existing, False
    return delivery, True


async def execute_slack_delivery(
    session: AsyncSession,
    settings: Settings,
    *,
    organization_id: UUID,
    user_id: UUID,
    role: MembershipRole,
    delivery_id: UUID,
    text: str,
) -> IntegrationDelivery:
    delivery = await session.scalar(
        select(IntegrationDelivery)
        .where(
            IntegrationDelivery.id == delivery_id,
            IntegrationDelivery.organization_id == organization_id,
        )
        .with_for_update()
    )
    if delivery is None:
        raise InvalidConfiguration("Integration delivery was not found")
    if delivery.status != "pending":
        return delivery

    connection = await get_connection_for_management(
        session,
        organization_id=organization_id,
        user_id=user_id,
        role=role,
        connection_id=delivery.connection_id,
    )
    try:
        credentials, _ = await active_credentials(
            session,
            settings,
            connection=connection,
        )
        result = await send_slack_message(credentials, text=text)
    except TerraSatchError as error:
        delivery.status = "failed"
        delivery.last_error = error.message[:1000]
        connection.last_error = delivery.last_error
        await session.flush()
        return delivery

    delivery.status = "delivered"
    delivery.external_id = result.external_id
    delivery.response_metadata = result.metadata
    delivery.last_error = None
    connection.last_error = None
    connection.last_synced_at = datetime.now(UTC)
    await session.flush()
    return delivery


async def execute_drive_export(
    session: AsyncSession,
    settings: Settings,
    *,
    organization_id: UUID,
    user_id: UUID,
    role: MembershipRole,
    delivery_id: UUID,
    name: str,
    content: str,
    mime_type: str,
) -> IntegrationDelivery:
    delivery = await session.scalar(
        select(IntegrationDelivery)
        .where(
            IntegrationDelivery.id == delivery_id,
            IntegrationDelivery.organization_id == organization_id,
        )
        .with_for_update()
    )
    if delivery is None:
        raise InvalidConfiguration("Integration delivery was not found")
    if delivery.status != "pending":
        return delivery

    connection = await get_connection_for_management(
        session,
        organization_id=organization_id,
        user_id=user_id,
        role=role,
        connection_id=delivery.connection_id,
    )
    folder_id = dict(connection.configuration or {}).get("folder_id")
    if folder_id is not None and not isinstance(folder_id, str):
        raise InvalidConfiguration("Stored Google Drive folder ID is invalid")

    try:
        credentials, _ = await active_credentials(
            session,
            settings,
            connection=connection,
        )
        result = await create_google_drive_file(
            credentials,
            name=name,
            content=content,
            mime_type=mime_type,
            folder_id=folder_id,
        )
    except TerraSatchError as error:
        delivery.status = "failed"
        delivery.last_error = error.message[:1000]
        connection.last_error = delivery.last_error
        await session.flush()
        return delivery

    delivery.status = "delivered"
    delivery.external_id = result.external_id
    delivery.response_metadata = result.metadata
    delivery.last_error = None
    connection.last_error = None
    connection.last_synced_at = datetime.now(UTC)
    await session.flush()
    return delivery


def content_metadata(content: str, **metadata: object) -> dict[str, object]:
    encoded = content.encode("utf-8")
    return {
        **metadata,
        "content_bytes": len(encoded),
        "content_sha256": hashlib.sha256(encoded).hexdigest(),
    }
