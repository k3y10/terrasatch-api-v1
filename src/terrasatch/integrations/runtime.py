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
from .operations import (
    create_google_drive_file,
    query_arcgis_features,
    send_slack_message,
    validate_arcgis_feature_layer_url,
)


def _audience_subjects(
    *,
    organization_id: UUID,
    user_id: UUID | None,
    team_ids: tuple[UUID, ...],
    workflow_key: str | None,
) -> set[tuple[str, str]]:
    subjects = {("organization", str(organization_id))}
    if user_id is not None:
        subjects.add(("user", str(user_id)))
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
    user_id: UUID | None,
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
    user_id: UUID | None,
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
    user_id: UUID | None,
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



async def query(
    session: AsyncSession,
    settings: Settings,
    *,
    organization_id: UUID,
    user_id: UUID | None,
    capability: str,
    payload: dict[str, object],
    team_ids: tuple[UUID, ...] = (),
    agent_key: str | None = "satchy",
    workflow_key: str | None = None,
    connection_id: UUID | None = None,
) -> dict[str, object]:
    """Query an authorized read capability without exposing provider credentials."""

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
    if capability != "map.features.query" or connection.provider != "esri_arcgis":
        raise InvalidConfiguration(
            f"{connection.provider} does not implement the requested read capability"
        )

    configured_layers = dict(connection.configuration or {}).get("feature_layer_urls")
    if not isinstance(configured_layers, list) or not configured_layers:
        raise InvalidConfiguration("ArcGIS connection has no approved feature layers")
    approved_layers = {
        validate_arcgis_feature_layer_url(item)
        for item in configured_layers
        if isinstance(item, str)
    }
    requested_layer = payload.get("layer_url")
    if requested_layer is None and len(approved_layers) == 1:
        layer_url = next(iter(approved_layers))
    elif isinstance(requested_layer, str):
        layer_url = validate_arcgis_feature_layer_url(requested_layer)
    else:
        raise InvalidConfiguration(
            "map.features.query requires layer_url when multiple layers are approved"
        )
    if layer_url not in approved_layers:
        raise InvalidConfiguration("ArcGIS feature layer is not approved for this connection")

    where = payload.get("where", "1=1")
    out_fields = payload.get("out_fields", ["*"])
    return_geometry = payload.get("return_geometry", True)
    result_record_count = payload.get("result_record_count", 100)
    result_offset = payload.get("result_offset", 0)
    if not isinstance(where, str):
        raise InvalidConfiguration("ArcGIS where must be a string")
    if not isinstance(out_fields, list) or not all(
        isinstance(field, str) for field in out_fields
    ):
        raise InvalidConfiguration("ArcGIS out_fields must be a list of field names")
    if not isinstance(return_geometry, bool):
        raise InvalidConfiguration("ArcGIS return_geometry must be boolean")
    if not isinstance(result_record_count, int) or isinstance(
        result_record_count,
        bool,
    ):
        raise InvalidConfiguration("ArcGIS result_record_count must be an integer")
    if not isinstance(result_offset, int) or isinstance(result_offset, bool):
        raise InvalidConfiguration("ArcGIS result_offset must be an integer")

    try:
        credentials, _ = await active_credentials(
            session,
            settings,
            connection=connection,
        )
        result = await query_arcgis_features(
            credentials,
            layer_url=layer_url,
            where=where,
            out_fields=out_fields,
            return_geometry=return_geometry,
            result_record_count=result_record_count,
            result_offset=result_offset,
        )
    except TerraSatchError as error:
        connection.last_error = error.message[:1000]
        await session.flush()
        raise

    connection.last_error = None
    connection.last_synced_at = datetime.now(UTC)
    await session.flush()
    return {
        "capability": capability,
        "connection_id": str(connection.id),
        "data": result.data,
        "metadata": result.metadata,
    }
