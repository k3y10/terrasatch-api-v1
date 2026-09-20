"""Capability-based integration runtime used by Satchy and workspace workflows."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.config import Settings
from terrasatch.errors import InvalidConfiguration, ResourceNotFound, TerraSatchError

from .models import (
    IntegrationConnection,
    IntegrationDelivery,
    IntegrationGrant,
    IntegrationStatus,
)
from .oauth_service import active_credentials
from .operations import create_google_drive_file, send_slack_message


def _audience_subjects(
    *,
    organization_id: UUID,
    user_id: UUID,
    team_ids: tuple[UUID, ...],
    workflow_key: str | None,
) -> set[tuple[str, str]]:
    subjects = {
        ("user", str(user_id)),
        ("organization", str(organization_id)),
    }
    subjects.update(("team", str(team_id)) for team_id in team_ids)
    if workflow_key:
        subjects.add(("workflow", workflow_key))
    return subjects


def _has_capability(grant: IntegrationGrant, capability: str) -> bool:
    return grant.enabled and capability in list(grant.capabilities or [])


async def resolve_connection(
    session: AsyncSession,
    *,
    organization_id: UUID,
    user_id: UUID,
    capability: str,
    team_ids: tuple[UUID, ...] = (),
    agent_key: str | None = "satchy",
    workflow_key: str | None = None,
    connection_id: UUID | None = None,
) -> IntegrationConnection:
    """Resolve a connected provider by capability rather than by provider brand."""

    query = select(IntegrationConnection).where(
        IntegrationConnection.organization_id == organization_id,
        IntegrationConnection.enabled.is_(True),
        IntegrationConnection.status == IntegrationStatus.CONNECTED.value,
    )
    if connection_id is not None:
        query = query.where(IntegrationConnection.id == connection_id)
    connections = list(await session.scalars(query))
    if not connections:
        raise ResourceNotFound("No connected integration provides this capability")

    ids = [connection.id for connection in connections]
    grants = list(
        await session.scalars(
            select(IntegrationGrant).where(
                IntegrationGrant.organization_id == organization_id,
                IntegrationGrant.connection_id.in_(ids),
                IntegrationGrant.enabled.is_(True),
            )
        )
    )
    grants_by_connection: dict[UUID, list[IntegrationGrant]] = {}
    for grant in grants:
        grants_by_connection.setdefault(grant.connection_id, []).append(grant)

    audience = _audience_subjects(
        organization_id=organization_id,
        user_id=user_id,
        team_ids=team_ids,
        workflow_key=workflow_key,
    )
    priority = {"user": 0, "team": 1, "workflow": 2, "organization": 3}
    eligible: list[tuple[int, datetime, IntegrationConnection]] = []

    for connection in connections:
        connection_grants = grants_by_connection.get(connection.id, [])
        audience_grants = [
            grant
            for grant in connection_grants
            if (grant.subject_type, grant.subject_id) in audience
            and _has_capability(grant, capability)
        ]
        if not audience_grants:
            continue
        if agent_key is not None:
            agent_allowed = any(
                grant.subject_type == "agent"
                and grant.subject_id == agent_key
                and _has_capability(grant, capability)
                for grant in connection_grants
            )
            if not agent_allowed:
                continue
        score = min(priority.get(grant.subject_type, 99) for grant in audience_grants)
        eligible.append((score, connection.created_at, connection))

    if not eligible:
        raise ResourceNotFound("No authorized integration provides this capability")
    eligible.sort(key=lambda item: (item[0], item[1]))
    return eligible[0][2]


def _content_metadata(content: str, **metadata: object) -> dict[str, object]:
    encoded = content.encode("utf-8")
    return {
        **metadata,
        "content_bytes": len(encoded),
        "content_sha256": hashlib.sha256(encoded).hexdigest(),
    }


async def _delivery(
    session: AsyncSession,
    *,
    organization_id: UUID,
    connection: IntegrationConnection,
    user_id: UUID,
    request_id: UUID,
    capability: str,
    request_metadata: dict[str, object],
) -> tuple[IntegrationDelivery, bool]:
    existing = await session.scalar(
        select(IntegrationDelivery).where(
            IntegrationDelivery.organization_id == organization_id,
            IntegrationDelivery.connection_id == connection.id,
            IntegrationDelivery.request_id == request_id,
        )
    )
    if existing is not None:
        return existing, False

    delivery = IntegrationDelivery(
        organization_id=organization_id,
        connection_id=connection.id,
        requested_by_user_id=user_id,
        request_id=request_id,
        operation=capability,
        status="pending",
        request_metadata=request_metadata,
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
                IntegrationDelivery.connection_id == connection.id,
                IntegrationDelivery.request_id == request_id,
            )
        )
        if existing is None:
            raise
        return existing, False
    return delivery, True


async def execute(
    session: AsyncSession,
    settings: Settings,
    *,
    organization_id: UUID,
    user_id: UUID,
    capability: str,
    request_id: UUID,
    payload: dict[str, object],
    team_ids: tuple[UUID, ...] = (),
    agent_key: str | None = "satchy",
    workflow_key: str | None = None,
    connection_id: UUID | None = None,
) -> IntegrationDelivery:
    """Execute one capability through the best authorized connected provider."""

    connection = await resolve_connection(
        session,
        organization_id=organization_id,
        user_id=user_id,
        capability=capability,
        team_ids=team_ids,
        agent_key=agent_key,
        workflow_key=workflow_key,
        connection_id=connection_id,
    )

    if capability == "notification.send":
        text = payload.get("text")
        if not isinstance(text, str):
            raise InvalidConfiguration("notification.send requires text")
        metadata = _content_metadata(text, character_count=len(text))
    elif capability == "document.create":
        name = payload.get("name")
        content = payload.get("content")
        mime_type = payload.get("mime_type", "text/plain")
        if not isinstance(name, str) or not isinstance(content, str):
            raise InvalidConfiguration("document.create requires name and content")
        if not isinstance(mime_type, str):
            raise InvalidConfiguration("document.create mime_type must be a string")
        metadata = _content_metadata(content, name=name, mime_type=mime_type)
    else:
        raise InvalidConfiguration(f"Unsupported integration capability: {capability}")

    delivery, created = await _delivery(
        session,
        organization_id=organization_id,
        connection=connection,
        user_id=user_id,
        request_id=request_id,
        capability=capability,
        request_metadata=metadata,
    )
    if not created:
        return delivery

    try:
        credentials, _ = await active_credentials(
            session,
            settings,
            connection=connection,
        )
        if capability == "notification.send" and connection.provider == "slack":
            result = await send_slack_message(credentials, text=text)
        elif capability == "document.create" and connection.provider == "google_drive":
            folder_id = dict(connection.configuration or {}).get("folder_id")
            if folder_id is not None and not isinstance(folder_id, str):
                raise InvalidConfiguration("Stored Google Drive folder ID is invalid")
            result = await create_google_drive_file(
                credentials,
                name=name,
                content=content,
                mime_type=mime_type,
                folder_id=folder_id,
            )
        else:
            raise InvalidConfiguration(
                f"{connection.provider} does not implement {capability}"
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
