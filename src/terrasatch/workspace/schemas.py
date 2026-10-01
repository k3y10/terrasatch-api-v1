"""Explicit workspace response contracts used by OpenAPI and generated SDK clients."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from terrasatch.billing.schemas import SubscriptionResponse


class WorkspaceOrganizationSummary(BaseModel):
    id: UUID
    name: str
    role: str


class WorkspaceUserSummary(BaseModel):
    id: UUID
    name: str
    email: str


class WorkspaceSessionResponse(BaseModel):
    user: WorkspaceUserSummary | None
    organizations: list[WorkspaceOrganizationSummary] = Field(default_factory=list)
    csrf_token: str


class WorkspaceLoginResponse(BaseModel):
    csrf_token: str


class WorkspaceLogoutResponse(BaseModel):
    signed_out: bool = True


class WorkspacePreferencesResponse(BaseModel):
    modules: list[str] = Field(default_factory=list)
    satchy: dict[str, object] = Field(default_factory=dict)


class WorkspaceDiscoveryPhases(BaseModel):
    listen: Literal["off", "active", "testing", "ready"]
    watch: Literal["off", "active", "testing", "ready"]
    learn: Literal["off", "active", "testing", "ready"]
    adapt: Literal["off", "active", "testing", "ready"]


class WorkspaceDiscoveryWorkflowCounts(BaseModel):
    identified: int = Field(ge=0)
    testing: int = Field(ge=0)
    approved: int = Field(ge=0)


class WorkspaceDiscoveryState(BaseModel):
    status: Literal["not_started", "active", "complete", "integrated"]
    duration_days: int = Field(ge=1)
    day: int = Field(ge=0)
    phases: WorkspaceDiscoveryPhases
    workflow_counts: WorkspaceDiscoveryWorkflowCounts


class WorkspaceProfileResponse(BaseModel):
    operational_domain: str
    workspace_template: str
    runtime_mode: Literal["legacy", "shadow", "agent_read", "agent_propose"]
    recommended_modules: list[str] = Field(default_factory=list)
    preferred_map_layers: list[str] = Field(default_factory=list)
    workflow_preferences: list[str] = Field(default_factory=list)
    discovery_state: WorkspaceDiscoveryState


class WorkspaceEdgeCapabilityDevice(BaseModel):
    id: UUID
    site_id: UUID
    name: str
    agent_version: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    last_seen_at: datetime | None = None


class WorkspaceCapabilityPolicy(BaseModel):
    agent_reads_enabled: bool
    agent_proposals_enabled: bool
    shadow_only: bool
    consequential_actions_require_approval: bool
    physical_actions_require_approval: bool


class WorkspaceCapabilityManifest(BaseModel):
    runtime_mode: Literal["legacy", "shadow", "agent_read", "agent_propose"]
    read: list[str] = Field(default_factory=list)
    write: list[str] = Field(default_factory=list)
    edge: list[str] = Field(default_factory=list)
    physical: list[str] = Field(default_factory=list)
    connected_providers: list[str] = Field(default_factory=list)
    edge_devices: list[WorkspaceEdgeCapabilityDevice] = Field(default_factory=list)
    policy: WorkspaceCapabilityPolicy


class WorkspaceConvergenceResponse(BaseModel):
    profile: WorkspaceProfileResponse
    capability_manifest: WorkspaceCapabilityManifest


class WorkspaceConvergenceUpdateResponse(BaseModel):
    profile: WorkspaceProfileResponse


class WorkspaceDeviceSummary(BaseModel):
    id: UUID
    name: str
    enabled: bool
    last_seen_at: datetime | None = None
    agent_version: str | None = None


class WorkspaceEngineSummary(BaseModel):
    provider: str
    model: str


class WorkspaceCapabilityResponse(BaseModel):
    key: str
    label: str
    access: Literal["read", "write"]


class WorkspaceIntegrationCatalogItem(BaseModel):
    key: str
    name: str
    category: str
    auth: str
    setup_status: Literal["managed", "planned", "available"]
    support_status: Literal[
        "managed",
        "supported",
        "partner_required",
        "coming_soon",
    ]
    connect_status: Literal[
        "managed",
        "available",
        "external_setup_required",
        "needs_configuration",
        "partner_required",
        "coming_soon",
    ]
    scopes: list[str] = Field(default_factory=list)
    allowed_scopes: list[str] = Field(default_factory=list)
    allowed: bool
    can_connect: bool
    requires_admin: bool
    connected: bool
    connected_scopes: list[str] = Field(default_factory=list)
    runtime_ready: bool
    capabilities: list[str] = Field(default_factory=list)
    capability_details: list[WorkspaceCapabilityResponse] = Field(default_factory=list)
    description: str


class WorkspaceIntegrationsResponse(BaseModel):
    devices: list[WorkspaceDeviceSummary] = Field(default_factory=list)
    engine: WorkspaceEngineSummary
    catalog: list[WorkspaceIntegrationCatalogItem] = Field(default_factory=list)
    connections: list[dict[str, object]] = Field(default_factory=list)


class WorkspaceSiteSummary(BaseModel):
    id: UUID
    name: str


class WorkspaceTeamSummary(BaseModel):
    id: UUID
    name: str
    site_id: UUID | None = None


class WorkspaceFieldAssetResponse(BaseModel):
    id: UUID
    site_id: UUID | None = None
    team_id: UUID | None = None
    owner_user_id: UUID | None = None
    controller_edge_device_id: UUID | None = None
    name: str
    type: str
    provider: str
    capabilities: list[str] = Field(default_factory=list)
    state: str
    location: dict[str, object] = Field(default_factory=dict)
    policy: dict[str, object] = Field(default_factory=dict)
    enabled: bool


class WorkspaceRecordInterpretation(BaseModel):
    id: UUID
    summary: str
    type: str
    latitude: float | None = None
    longitude: float | None = None
    location: str | None = None
    confidence: float
    spatial_status: str | None = None


class WorkspaceRecordResponse(BaseModel):
    id: UUID
    source: str
    speaker: str | None = None
    timestamp: datetime
    original: str | None = None
    location: object | None = None
    interpretations: list[WorkspaceRecordInterpretation] = Field(default_factory=list)


class WorkspaceActionResponse(BaseModel):
    id: UUID
    source_id: UUID | None = None
    type: str
    reason: str
    message: str | None = None
    status: str
    integration_execution: dict[str, object] = Field(default_factory=dict)


class WorkspaceMessageResponse(BaseModel):
    id: UUID
    role: Literal["user", "assistant"]
    content: str


class WorkspaceSnapshotResponse(BaseModel):
    role: str
    modules: list[str] = Field(default_factory=list)
    satchy_preferences: dict[str, object] = Field(default_factory=dict)
    convergence: WorkspaceConvergenceResponse
    integrations: WorkspaceIntegrationsResponse
    subscription: SubscriptionResponse
    sites: list[WorkspaceSiteSummary] = Field(default_factory=list)
    teams: list[WorkspaceTeamSummary] = Field(default_factory=list)
    assets: list[WorkspaceFieldAssetResponse] = Field(default_factory=list)
    records: list[WorkspaceRecordResponse] = Field(default_factory=list)
    actions: list[WorkspaceActionResponse] = Field(default_factory=list)
    messages: list[WorkspaceMessageResponse] = Field(default_factory=list)


class SatchyChatResponse(BaseModel):
    answer: str
    action_id: UUID | None = None
    action_status: str | None = None
    approval_required: bool
    run_id: UUID
    run_status: str


class WorkspaceActionReviewResponse(BaseModel):
    id: UUID
    status: str
    integration_detail: object | None = None
    integration_execution: dict[str, object] = Field(default_factory=dict)


class WorkspaceObservationResponse(BaseModel):
    id: UUID
