"""External field-source endpoints that do not use TerraSatch API-key auth."""

from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import ValidationError

from terrasatch.config import Settings
from terrasatch.database.session import create_session_factory
from terrasatch.errors import AuthenticationFailed

from .schemas import GarminIngestResponse, GarminIpcPayload
from .service import (
    authenticate_garmin_connection,
    ingest_garmin_payload,
    resolve_garmin_connection,
)

router = APIRouter(prefix="/field", tags=["field-inputs"])

_MAX_GARMIN_BODY_BYTES = 20_000_000


def _garmin_static_token(request: Request) -> str | None:
    explicit = request.headers.get("X-Garmin-Token")
    if explicit:
        return explicit.strip() or None

    authorization = request.headers.get("Authorization")
    if not authorization:
        return None
    scheme, separator, value = authorization.partition(" ")
    if separator and scheme.casefold() == "bearer":
        return value.strip() or None
    # Garmin's public IPC guide specifies a static token in HTTP headers but
    # does not prescribe one header format. Accept a raw Authorization value
    # so Portal Connect can be configured without a TerraSatch-specific header.
    return authorization.strip() or None


@router.post(
    "/garmin/inreach/{connection_id}",
    response_model=GarminIngestResponse,
)
async def post_garmin_inreach(
    connection_id: UUID,
    request: Request,
) -> GarminIngestResponse:
    settings: Settings = request.app.state.settings
    provided_token = _garmin_static_token(request)
    if not provided_token:
        raise AuthenticationFailed("Garmin inReach authorization is required")

    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().casefold()
    if content_type != "application/json":
        raise HTTPException(status_code=415, detail="Garmin IPC payload must be JSON")

    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > _MAX_GARMIN_BODY_BYTES:
                raise HTTPException(status_code=413, detail="Garmin IPC payload is too large")
        except ValueError as error:
            raise HTTPException(status_code=400, detail="Invalid Content-Length") from error

    session_factory = create_session_factory(settings)
    async with session_factory() as session:
        try:
            connection = await resolve_garmin_connection(
                session,
                connection_id=connection_id,
            )
            await authenticate_garmin_connection(
                session,
                settings,
                connection=connection,
                provided_token=provided_token,
            )

            raw = await request.body()
            if len(raw) > _MAX_GARMIN_BODY_BYTES:
                raise HTTPException(status_code=413, detail="Garmin IPC payload is too large")
            try:
                document = json.loads(raw)
                payload = GarminIpcPayload.model_validate(document)
            except (json.JSONDecodeError, ValidationError) as error:
                raise HTTPException(
                    status_code=422,
                    detail="Invalid Garmin IPC payload",
                ) from error

            batch = await ingest_garmin_payload(
                session,
                settings,
                connection=connection,
                payload=payload,
            )
            await session.commit()
        except Exception:
            await session.rollback()
            raise

    return GarminIngestResponse(
        accepted=len(batch.transmissions),
        duplicates=batch.duplicates,
        transmissions=[item.id for item in batch.transmissions],
        operational_events=len(batch.events),
    )
