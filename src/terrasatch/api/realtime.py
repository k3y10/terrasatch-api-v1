"""Authorized tenant-scoped realtime subscriptions for TerraSatch operational events."""

from __future__ import annotations

import asyncio
import json

import structlog
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from redis.asyncio import Redis

from terrasatch.auth.dependencies import Principal, authenticate_token
from terrasatch.events.bus import organization_channel

router = APIRouter(tags=["realtime"])
logger = structlog.get_logger(__name__)

_ALLOWED_TOPICS = {"events", "transmissions", "transcripts"}
_TOPIC_SCOPES = {
    "events": "read:events",
    "transmissions": "read:transmissions",
    "transcripts": "read:transcripts",
}


def _authorized_topics(principal: Principal, requested: list[str]) -> set[str]:
    topics = {topic for topic in requested if topic in _ALLOWED_TOPICS}
    if not topics:
        return set()
    if "admin" in principal.scopes:
        return topics
    return {topic for topic in topics if _TOPIC_SCOPES[topic] in principal.scopes}


@router.websocket("/ws/v1/events")
async def events_websocket(websocket: WebSocket) -> None:
    """Authenticate then relay normalized Redis events for only the caller's tenant.

    Clients send a first message shaped like:

    ``{"action":"subscribe","token":"ts_...","topics":["events","transmissions"]}``

    Keeping the token out of the URL reduces accidental credential exposure in proxy/access logs.
    """

    await websocket.accept()
    client: Redis | None = None
    pubsub = None
    try:
        first = await asyncio.wait_for(websocket.receive_json(), timeout=10)
        if not isinstance(first, dict) or first.get("action") != "subscribe":
            await websocket.send_json({"error": "First message must be a subscribe request"})
            await websocket.close(code=4400)
            return

        token = first.get("token")
        requested = first.get("topics", ["events"])
        if not isinstance(token, str) or not isinstance(requested, list) or not all(
            isinstance(item, str) for item in requested
        ):
            await websocket.send_json({"error": "Invalid subscription request"})
            await websocket.close(code=4400)
            return

        try:
            principal = await authenticate_token(websocket.app.state.settings, token)
        except HTTPException:
            await websocket.send_json({"error": "Authentication failed"})
            await websocket.close(code=4401)
            return

        topics = _authorized_topics(principal, requested)
        if not topics:
            await websocket.send_json({"error": "API key does not permit requested topics"})
            await websocket.close(code=4403)
            return

        client = Redis.from_url(
            str(websocket.app.state.settings.redis_url),
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        pubsub = client.pubsub()
        await pubsub.subscribe(organization_channel(principal.organization_id))
        await websocket.send_json(
            {
                "type": "subscription.ready",
                "topics": sorted(topics),
                "organization_id": str(principal.organization_id),
            }
        )

        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message is None:
                await asyncio.sleep(0.05)
                continue
            raw = message.get("data")
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            try:
                payload = json.loads(raw) if isinstance(raw, str) else raw
            except json.JSONDecodeError:
                logger.warning("realtime.invalid_event_payload")
                continue
            if isinstance(payload, dict) and payload.get("topic") in topics:
                await websocket.send_json(payload)
    except TimeoutError:
        await websocket.close(code=4408)
    except WebSocketDisconnect:
        return
    finally:
        if pubsub is not None:
            await pubsub.aclose()
        if client is not None:
            await client.aclose()
