"""Redis-backed normalized event publication used by realtime clients and future webhooks."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID

from redis.asyncio import Redis

from terrasatch.config import Settings


def organization_channel(organization_id: UUID) -> str:
    return f"terrasatch:org:{organization_id}:events"


async def publish_event(
    settings: Settings,
    *,
    organization_id: UUID,
    topic: str,
    event_type: str,
    payload: dict[str, object],
) -> None:
    """Publish one normalized tenant-scoped event without leaking Redis details to callers."""

    message = {
        "topic": topic,
        "type": event_type,
        "timestamp": datetime.now(UTC).isoformat(),
        "organization_id": str(organization_id),
        "payload": payload,
    }
    client = Redis.from_url(str(settings.redis_url), socket_connect_timeout=2, socket_timeout=2)
    try:
        await client.publish(
            organization_channel(organization_id), json.dumps(message, default=str)
        )
    finally:
        await client.aclose()
