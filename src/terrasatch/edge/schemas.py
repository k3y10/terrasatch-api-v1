"""API schemas for Edge pairing, inventory, heartbeat, and remote configuration."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

MAX_EDGE_TELEMETRY_BYTES = 16 * 1024


def _validate_telemetry_payload(value: dict[str, object]) -> dict[str, object]:
    """Keep heartbeat telemetry compact while allowing forward-compatible namespaces."""

    try:
        encoded = json.dumps(
            value,
            separators=(",", ":"),
            sort_keys=True,
            ensure_ascii=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("telemetry must be JSON-serializable") from exc
    if len(encoded) > MAX_EDGE_TELEMETRY_BYTES:
        raise ValueError(f"telemetry must not exceed {MAX_EDGE_TELEMETRY_BYTES} serialized bytes")
    return value


class PairingStartRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    hostname: str | None = Field(default=None, max_length=255)
    platform: str | None = Field(default=None, max_length=100)
    architecture: str | None = Field(default=None, max_length=100)
    agent_version: str | None = Field(default=None, max_length=64)


class PairingStartResponse(BaseModel):
    pairing_id: UUID
    device_code: str
    user_code: str
    verification_url: str
    expires_at: datetime
    interval_seconds: int = 5


class PairingApproveRequest(BaseModel):
    site_id: UUID


class PairingTokenRequest(BaseModel):
    device_code: str = Field(min_length=20, max_length=200)


class DeviceResponse(BaseModel):
    id: UUID
    organization_id: UUID
    site_id: UUID
    name: str
    hostname: str | None
    platform: str | None
    architecture: str | None
    agent_version: str | None
    hardware_inventory: list[dict[str, object]]
    capabilities: list[str]
    remote_config: dict[str, object]
    telemetry: dict[str, object] = Field(default_factory=dict)
    enabled: bool
    last_seen_at: datetime | None
    created_at: datetime
    updated_at: datetime


class PairingTokenResponse(BaseModel):
    status: Literal["pending", "approved", "expired", "claimed"]
    token: str | None = None
    device: DeviceResponse | None = None


class EdgeHeartbeatRequest(BaseModel):
    agent_version: str | None = Field(default=None, max_length=64)
    hardware_inventory: list[dict[str, object]] = Field(default_factory=list, max_length=256)
    capabilities: list[str] = Field(default_factory=list, max_length=128)
    telemetry: dict[str, object] = Field(default_factory=dict)

    @field_validator("telemetry")
    @classmethod
    def validate_telemetry(cls, value: dict[str, object]) -> dict[str, object]:
        return _validate_telemetry_payload(value)


class EdgeHeartbeatResponse(BaseModel):
    device: DeviceResponse
    server_time: datetime


class EdgeDeviceUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    site_id: UUID | None = None
    enabled: bool | None = None
    remote_config: dict[str, object] | None = None


class EdgeCommandResponse(BaseModel):
    id: UUID
    organization_id: UUID
    site_id: UUID
    edge_device_id: UUID
    command_type: str
    payload: dict[str, object]
    priority: int
    status: str
    created_at: datetime
    expires_at: datetime | None
    acknowledged_at: datetime | None
    completed_at: datetime | None


class EdgeCommandResultRequest(BaseModel):
    status: Literal["simulated", "failed"]
    detail: str | None = Field(default=None, max_length=2000)
