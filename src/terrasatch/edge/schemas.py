"""API schemas for Edge pairing, inventory, heartbeat, and remote configuration."""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


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


class EdgeHeartbeatResponse(BaseModel):
    device: DeviceResponse
    server_time: datetime


class EdgeDeviceUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    site_id: UUID | None = None
    enabled: bool | None = None
    remote_config: dict[str, object] | None = None
