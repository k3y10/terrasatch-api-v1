"""Small authenticated client used by local receive-side edge tooling."""

from __future__ import annotations

import os
from dataclasses import dataclass
from uuid import UUID, uuid4

import httpx


@dataclass(frozen=True, slots=True)
class EdgeApiClient:
    base_url: str
    api_key: str
    timeout_seconds: float = 10.0

    @classmethod
    def from_environment(cls, *, base_url: str | None = None) -> EdgeApiClient:
        key = os.getenv("TERRASATCH_EDGE_API_KEY", "").strip()
        if not key:
            raise RuntimeError("TERRASATCH_EDGE_API_KEY is not set")
        resolved_url = (base_url or os.getenv("TERRASATCH_API_BASE_URL") or "").strip().rstrip("/")
        if not resolved_url:
            raise RuntimeError("TERRASATCH_API_BASE_URL is not set")
        return cls(base_url=resolved_url, api_key=key)

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}

    def check(self) -> dict[str, object]:
        with httpx.Client(base_url=self.base_url, headers=self.headers, timeout=self.timeout_seconds) as client:
            response = client.get("/api/v1/auth/me")
            response.raise_for_status()
            return response.json()

    def submit_text(
        self,
        *,
        site_id: UUID,
        text: str,
        callsign: str | None = None,
        agent_id: UUID | None = None,
        channel_id: UUID | None = None,
        source_message_id: str | None = None,
        source: str = "edge-rtl",
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "site_id": str(site_id),
            "text": text,
            "source": source,
            "source_message_id": source_message_id or f"edge-{uuid4()}",
        }
        if callsign:
            payload["callsign"] = callsign
        if agent_id:
            payload["agent_id"] = str(agent_id)
        if channel_id:
            payload["channel_id"] = str(channel_id)

        with httpx.Client(base_url=self.base_url, headers=self.headers, timeout=self.timeout_seconds) as client:
            response = client.post("/api/v1/transmissions", json=payload)
            response.raise_for_status()
            return response.json()
