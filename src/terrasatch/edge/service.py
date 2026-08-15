"""Edge pairing and device lifecycle services."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.auth.service import issue_api_key
from terrasatch.config import Settings
from terrasatch.edge.codes import (
    generate_device_code,
    generate_user_code,
    hash_device_code,
    normalize_user_code,
)
from terrasatch.edge.models import EdgeDevice, EdgePairing
from terrasatch.edge.schemas import EdgeDeviceUpdateRequest, EdgeHeartbeatRequest, PairingStartRequest
from terrasatch.errors import InvalidConfiguration, ResourceNotFound
from terrasatch.organizations.service import get_site

PAIRING_TTL_MINUTES = 10
DEVICE_SCOPES = ("edge:connect", "edge:ingest", "read:sites")


async def start_pairing(
    session: AsyncSession,
    payload: PairingStartRequest,
) -> tuple[EdgePairing, str]:
    device_code = generate_device_code()
    pairing = EdgePairing(
        device_code_hash=hash_device_code(device_code),
        user_code=generate_user_code(),
        requested_name=payload.name.strip(),
        hostname=payload.hostname,
        platform=payload.platform,
        architecture=payload.architecture,
        agent_version=payload.agent_version,
        expires_at=datetime.now(UTC) + timedelta(minutes=PAIRING_TTL_MINUTES),
    )
    session.add(pairing)
    await session.flush()
    return pairing, device_code


async def approve_pairing(
    session: AsyncSession,
    *,
    user_code: str,
    organization_id: UUID,
    api_key_id: UUID | None,
    site_id: UUID,
) -> EdgePairing:
    pairing = await session.scalar(
        select(EdgePairing)
        .where(EdgePairing.user_code == normalize_user_code(user_code))
        .with_for_update()
    )
    if pairing is None:
        raise ResourceNotFound("Edge pairing code was not found")
    now = datetime.now(UTC)
    if pairing.expires_at <= now:
        raise InvalidConfiguration("Edge pairing code has expired")
    if pairing.claimed_at is not None:
        raise InvalidConfiguration("Edge pairing code has already been claimed")
    if pairing.approved_at is not None:
        raise InvalidConfiguration("Edge pairing code has already been approved")
    await get_site(session, organization_id=organization_id, site_id=site_id)
    pairing.organization_id = organization_id
    pairing.site_id = site_id
    pairing.approved_by_api_key_id = api_key_id
    pairing.approved_at = now
    await session.flush()
    return pairing


async def claim_pairing(
    session: AsyncSession,
    *,
    settings: Settings,
    device_code: str,
) -> tuple[str, EdgeDevice | None, str | None]:
    pairing = await session.scalar(
        select(EdgePairing)
        .where(EdgePairing.device_code_hash == hash_device_code(device_code))
        .with_for_update()
    )
    if pairing is None:
        return "expired", None, None
    now = datetime.now(UTC)
    if pairing.expires_at <= now:
        return "expired", None, None
    if pairing.claimed_at is not None:
        return "claimed", None, None
    if pairing.approved_at is None or pairing.organization_id is None or pairing.site_id is None:
        return "pending", None, None

    api_key, generated = await issue_api_key(
        session,
        settings=settings,
        name=f"Edge: {pairing.requested_name}",
        scopes=DEVICE_SCOPES,
        organization_selector=str(pairing.organization_id),
    )
    device = EdgeDevice(
        organization_id=pairing.organization_id,
        site_id=pairing.site_id,
        api_key_id=api_key.id,
        name=pairing.requested_name,
        hostname=pairing.hostname,
        platform=pairing.platform,
        architecture=pairing.architecture,
        agent_version=pairing.agent_version,
    )
    session.add(device)
    pairing.claimed_at = now
    await session.flush()
    return "approved", device, generated.token


async def list_devices(
    session: AsyncSession,
    *,
    organization_id: UUID,
) -> list[EdgeDevice]:
    return list(
        await session.scalars(
            select(EdgeDevice)
            .where(EdgeDevice.organization_id == organization_id)
            .order_by(EdgeDevice.created_at.desc())
        )
    )


async def get_device(
    session: AsyncSession,
    *,
    organization_id: UUID,
    device_id: UUID,
) -> EdgeDevice:
    device = await session.scalar(
        select(EdgeDevice).where(
            EdgeDevice.id == device_id,
            EdgeDevice.organization_id == organization_id,
        )
    )
    if device is None:
        raise ResourceNotFound("Edge device was not found")
    return device


async def get_device_for_api_key(
    session: AsyncSession,
    *,
    organization_id: UUID,
    api_key_id: UUID,
) -> EdgeDevice:
    device = await session.scalar(
        select(EdgeDevice).where(
            EdgeDevice.organization_id == organization_id,
            EdgeDevice.api_key_id == api_key_id,
        )
    )
    if device is None or not device.enabled:
        raise ResourceNotFound("Edge device was not found for this credential")
    return device


async def heartbeat_device(
    session: AsyncSession,
    *,
    organization_id: UUID,
    api_key_id: UUID,
    payload: EdgeHeartbeatRequest,
) -> EdgeDevice:
    device = await get_device_for_api_key(
        session,
        organization_id=organization_id,
        api_key_id=api_key_id,
    )
    device.last_seen_at = datetime.now(UTC)
    if payload.agent_version:
        device.agent_version = payload.agent_version
    device.hardware_inventory = payload.hardware_inventory
    device.capabilities = sorted(set(payload.capabilities))
    await session.flush()
    return device


async def update_device(
    session: AsyncSession,
    *,
    organization_id: UUID,
    device_id: UUID,
    payload: EdgeDeviceUpdateRequest,
) -> EdgeDevice:
    device = await get_device(
        session,
        organization_id=organization_id,
        device_id=device_id,
    )
    if payload.site_id is not None:
        await get_site(
            session,
            organization_id=organization_id,
            site_id=payload.site_id,
        )
        device.site_id = payload.site_id
    if payload.name is not None:
        device.name = payload.name.strip()
    if payload.enabled is not None:
        device.enabled = payload.enabled
    if payload.remote_config is not None:
        device.remote_config = payload.remote_config
    await session.flush()
    return device
