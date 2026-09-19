"""Validated contracts shared by Satchy context, reasoning, and workflows."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class SatchyIntent(StrEnum):
    INFORMATION = "information"
    QUESTION = "question"
    LOG_OBSERVATION = "log_observation"
    CREATE_TASK = "create_task"
    SUMMARIZE = "summarize"
    REPEAT = "repeat"
    CLARIFY = "clarify"
    CORRECT_RECORD = "correct_record"
    APPROVE_ACTION = "approve_action"
    REJECT_ACTION = "reject_action"
    CANCEL_ACTION = "cancel_action"
    REQUEST_ACTION = "request_action"
    REQUEST_MISSION = "request_mission"
    MISSION_STATUS = "mission_status"
    ABORT_MISSION = "abort_mission"


class WorkflowMode(StrEnum):
    AUTO_COMPLETE = "auto_complete"
    CLARIFY = "clarify"
    CONFIRM = "confirm"


class ActiveMapContext(BaseModel):
    """Ephemeral UI context supplied by an authorized client; never inferred as fact."""

    map_id: str | None = Field(default=None, max_length=128)
    center_latitude: float | None = Field(default=None, ge=-90, le=90)
    center_longitude: float | None = Field(default=None, ge=-180, le=180)
    zoom: float | None = Field(default=None, ge=0, le=30)
    selected_layers: list[str] = Field(default_factory=list, max_length=64)
    selected_terrain: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def coordinate_pair(self):
        if (self.center_latitude is None) != (self.center_longitude is None):
            raise ValueError("Map center requires both latitude and longitude")
        return self


class IntentResolution(BaseModel):
    intent: SatchyIntent
    confidence: float = Field(ge=0, le=1)
    explicit: bool = False
    references_context: bool = False


class SatchyContext(BaseModel):
    """Tenant-safe context supplied to Satchy for one decision."""

    organization_id: UUID
    organization_name: str | None = None
    site_id: UUID
    site_name: str | None = None
    user_id: UUID | None = None
    user_name: str | None = None
    membership_role: str | None = None
    team_id: UUID | None = None
    team_name: str | None = None
    transmission_id: UUID | None = None
    conversation_id: UUID | None = None
    channel_id: UUID | None = None
    callsign: str | None = None
    objective: str | None = Field(default=None, max_length=2000)
    active_map: ActiveMapContext | None = None
    workspace_modules: list[str] = Field(default_factory=list)
    user_preferences: dict[str, object] = Field(default_factory=dict)
    operational_profile: dict[str, object] = Field(default_factory=dict)
    edge_context: dict[str, object] = Field(default_factory=dict)
    rf_context: dict[str, object] = Field(default_factory=dict)
    evidence: list[dict[str, object]] = Field(default_factory=list, max_length=64)


class SatchyDecision(BaseModel):
    intent: SatchyIntent
    workflow_mode: WorkflowMode
    understanding: str = Field(min_length=1, max_length=4000)
    confidence: float = Field(ge=0, le=1)
    organization_id: UUID
    site_id: UUID
    user_id: UUID | None = None
    team_id: UUID | None = None
    conversation_id: UUID | None = None
    evidence_ids: list[UUID] = Field(default_factory=list, max_length=64)
    missing_context: list[str] = Field(default_factory=list, max_length=32)
    workflow: dict[str, object] | None = None
    proposed_action: dict[str, object] | None = None
    proposed_mission: dict[str, object] | None = None
    approval_required: bool = False
    radio_response: str = Field(min_length=1, max_length=2000)
    provenance: dict[str, object] = Field(default_factory=dict)


class FieldAssetCreate(BaseModel):
    """Workspace contract for registering authorized infrastructure."""

    name: str = Field(min_length=1, max_length=255)
    asset_type: str = Field(min_length=1, max_length=100)
    provider: str = Field(min_length=1, max_length=100)
    site_id: UUID | None = None
    team_id: UUID | None = None
    owner_user_id: UUID | None = None
    controller_edge_device_id: UUID | None = None
    capabilities: list[str] = Field(default_factory=list, max_length=128)
    state: Literal["online", "available", "busy", "charging", "offline", "degraded"] = "offline"
    location: dict[str, object] = Field(default_factory=dict)
    policy: dict[str, object] = Field(default_factory=dict)
    enabled: bool = True


class FieldAssetUpdate(BaseModel):
    """Partial workspace update for a registered field asset."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    asset_type: str | None = Field(default=None, min_length=1, max_length=100)
    provider: str | None = Field(default=None, min_length=1, max_length=100)
    site_id: UUID | None = None
    team_id: UUID | None = None
    owner_user_id: UUID | None = None
    controller_edge_device_id: UUID | None = None
    capabilities: list[str] | None = Field(default=None, max_length=128)
    state: Literal["online", "available", "busy", "charging", "offline", "degraded"] | None = None
    location: dict[str, object] | None = None
    policy: dict[str, object] | None = None
    enabled: bool | None = None
