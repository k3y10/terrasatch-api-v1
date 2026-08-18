"""Public aggregate TerraSatch network status without tenant or device details."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from time import monotonic

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.config import Settings
from terrasatch.database.session import create_session_factory
from terrasatch.edge.models import EdgeDevice
from terrasatch.identity.models import Membership, User

ONLINE_AFTER_SECONDS = 120
_PUBLIC_CACHE_SECONDS = 15.0
_cache_lock = asyncio.Lock()
_cached_payload: dict[str, object] | None = None
_cached_key: tuple[str, int, int] | None = None
_cache_expires_at = 0.0


def capacity_state(percent: int) -> str:
    """Return a stable operator-facing capacity state for the highest utilized limit."""

    if percent >= 100:
        return "registration_paused"
    if percent >= 90:
        return "near_capacity"
    if percent >= 80:
        return "capacity_watch"
    return "healthy"


def _percent(value: int, limit: int) -> int:
    if limit <= 0:
        return 100
    return min(100, round((value / limit) * 100))


def _settings_cache_key(settings: Settings) -> tuple[str, int, int]:
    return (
        str(settings.database_url),
        settings.max_edge_devices,
        settings.max_portal_users,
    )


async def count_registered_edges(session: AsyncSession) -> int:
    """Count every registered Edge node, including disabled nodes."""

    return int(await session.scalar(select(func.count(EdgeDevice.id))) or 0)


async def count_portal_users(session: AsyncSession) -> int:
    """Count enabled human users with at least one enabled organization membership."""

    value = await session.scalar(
        select(func.count(func.distinct(User.id)))
        .join(Membership, Membership.user_id == User.id)
        .where(
            User.enabled.is_(True),
            Membership.enabled.is_(True),
        )
    )
    return int(value or 0)


async def build_public_network_status(
    session: AsyncSession,
    *,
    settings: Settings,
    now: datetime | None = None,
) -> dict[str, object]:
    """Build privacy-safe network growth and capacity counters for the public console."""

    reference = now or datetime.now(UTC)
    online_cutoff = reference - timedelta(seconds=ONLINE_AFTER_SECONDS)

    registered_nodes = await count_registered_edges(session)
    online_nodes = int(
        await session.scalar(
            select(func.count(EdgeDevice.id)).where(
                EdgeDevice.enabled.is_(True),
                EdgeDevice.last_seen_at.is_not(None),
                EdgeDevice.last_seen_at >= online_cutoff,
            )
        )
        or 0
    )
    field_sites = int(
        await session.scalar(
            select(func.count(func.distinct(EdgeDevice.site_id))).where(
                EdgeDevice.enabled.is_(True)
            )
        )
        or 0
    )
    members = await count_portal_users(session)

    node_percent = _percent(registered_nodes, settings.max_edge_devices)
    member_percent = _percent(members, settings.max_portal_users)
    capacity_percent = max(node_percent, member_percent)
    state = capacity_state(capacity_percent)

    return {
        "generated_at": reference.isoformat(),
        "registered_nodes": registered_nodes,
        "online_nodes": online_nodes,
        "field_sites": field_sites,
        "members": members,
        "limits": {
            "nodes": settings.max_edge_devices,
            "members": settings.max_portal_users,
        },
        "utilization": {
            "nodes_percent": node_percent,
            "members_percent": member_percent,
            "capacity_percent": capacity_percent,
        },
        "capacity_state": state,
        "node_registration_open": registered_nodes < settings.max_edge_devices,
        "member_registration_open": members < settings.max_portal_users,
    }


async def get_public_network_status(settings: Settings) -> dict[str, object]:
    """Return a short-lived cached aggregate for the public console."""

    global _cached_payload, _cached_key, _cache_expires_at

    key = _settings_cache_key(settings)
    current = monotonic()
    if _cached_payload is not None and _cached_key == key and current < _cache_expires_at:
        return dict(_cached_payload)

    async with _cache_lock:
        current = monotonic()
        if _cached_payload is not None and _cached_key == key and current < _cache_expires_at:
            return dict(_cached_payload)

        session_factory = create_session_factory(settings)
        async with session_factory() as session:
            payload = await build_public_network_status(session, settings=settings)

        _cached_payload = payload
        _cached_key = key
        _cache_expires_at = monotonic() + _PUBLIC_CACHE_SECONDS
        return dict(payload)
