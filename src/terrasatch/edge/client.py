"""Outbound-only client used by local edge receivers to submit authorized observations."""

from __future__ import annotations

from uuid import UUID, uuid4

import httpx


def submit_text_transmission(
    *,
    base_url: str,
    api_key: str,
    site_id: UUID,
    text: str,
    callsign: str | None = None,
    source: str = "edge-manual",
    timeout_seconds: float = 15.0,
) -> dict[str, object]:
    """Submit one text observation into the canonical TerraSatch transmission pipeline."""

    normalized_text = text.strip()
    if not normalized_text:
        raise ValueError("text cannot be blank")
    normalized_source = source.strip()
    if not normalized_source:
        raise ValueError("source cannot be blank")
    token = api_key.strip()
    if not token:
        raise ValueError("api_key cannot be blank")

    payload: dict[str, object] = {
        "site_id": str(site_id),
        "text": normalized_text,
        "source": normalized_source,
        "source_message_id": f"edge-{uuid4()}",
    }
    if callsign and callsign.strip():
        payload["callsign"] = callsign.strip()

    with httpx.Client(
        base_url=base_url.rstrip("/"),
        headers={"Authorization": f"Bearer {token}"},
        timeout=timeout_seconds,
    ) as client:
        response = client.post("/api/v1/transmissions", json=payload)
        response.raise_for_status()
        data = response.json()

    if not isinstance(data, dict):
        raise RuntimeError("TerraSatch API returned an unexpected response shape")
    return data
