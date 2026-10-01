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
    organizations: list[WorkspaceOrganizationSummary]
    csrf_token: str


class WorkspaceLoginResponse(BaseModel):
    csrf_token: str


class WorkspaceLogoutResponse(BaseModel):
    signed_out: bool


class WorkspacePreferencesResponse(BaseModel):
    modules: list[str]
    satchy: dict[str, object]


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
    recommended_modules: list[str]
    preferred_map_layers: list[str]
    workflow_preferences: list[str]
    discovery_state: WorkspaceDiscoveryState


class WorkspaceEdgeCapabilityDevice(BaseModel):
    id: UUID
    site_id: UUID
    name: str
    agent_version: str | None
    capabilities: list[str]
    last_seen_at: datetime | None


class WorkspaceCapabilityPolicy(BaseModel):
    agent_reads_enabled: bool
    agent_proposals_enabled: bool
    shadow_only: bool
    consequential_actions_require_approval: bool
    physical_actions_require_approval: bool


class WorkspaceCapabilityManifest(BaseModel):
    runtime_mode: Literal["legacy", "shadow", "agent_read", "agent_propose"]
    read: list[str]
    write: list[str]
    edge: list[str]
    physical: list[str]
    connected_providers: list[str]
    edge_devices: list[WorkspaceEdgeCapabilityDevice]
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
    last_seen_at: datetime | None
    agent_version: str | None


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
    scopes: list[str]
    allowed_scopes: list[str]
    allowed: bool
    can_connect: bool
    requires_admin: bool
    connected: bool
    connected_scopes: list[str]
    runtime_ready: bool
    capabilities: list[str]
    capability_details: list[WorkspaceCapabilityResponse]
    description: str


class WorkspaceIntegrationsResponse(BaseModel):
    devices: list[WorkspaceDeviceSummary]
    engine: WorkspaceEngineSummary
    catalog: list[WorkspaceIntegrationCatalogItem]
    connections: list[dict[str, object]]


class WorkspaceSiteSummary(BaseModel):
    id: UUID
    name: str


class WorkspaceTeamSummary(BaseModel):
    id: UUID
    name: str
    site_id: UUID | None


class WorkspaceFieldAssetResponse(BaseModel):
    id: UUID
    site_id: UUID | None
    team_id: UUID | None
    owner_user_id: UUID | None
    controller_edge_device_id: UUID | None
    name: str
    type: str
    provider: str
    capabilities: list[str]
    state: str
    location: dict[str, object]
    policy: dict[str, object]
    enabled: bool


class WorkspaceRecordInterpretation(BaseModel):
    id: UUID
    summary: str
    type: str
    latitude: float | None
    longitude: float | None
    location: str | None
    confidence: float
    spatial_status: str | None


class WorkspaceRecordResponse(BaseModel):
    id: UUID
    source: str
    speaker: str | None
    timestamp: datetime
    original: str | None
    location: object | None
    interpretations: list[WorkspaceRecordInterpretation]


class WorkspaceActionResponse(BaseModel):
    id: UUID
    source_id: UUID | None
    type: str
    reason: str
    message: str | None
    status: str
    integration_execution: dict[str, object]


class WorkspaceMessageResponse(BaseModel):
    id: UUID
    role: Literal["user", "assistant"]
    content: str


class WorkspaceSnapshotResponse(BaseModel):
    role: str
    modules: list[str]
    satchy_preferences: dict[str, object]
    convergence: WorkspaceConvergenceResponse
    integrations: WorkspaceIntegrationsResponse
    subscription: SubscriptionResponse
    sites: list[WorkspaceSiteSummary]
    teams: list[WorkspaceTeamSummary]
    assets: list[WorkspaceFieldAssetResponse]
    records: list[WorkspaceRecordResponse]
    actions: list[WorkspaceActionResponse]
    messages: list[WorkspaceMessageResponse]


class SatchyChatResponse(BaseModel):
    answer: str
    action_id: UUID | None
    action_status: str | None
    approval_required: bool
    run_id: UUID
    run_status: str


class WorkspaceActionReviewResponse(BaseModel):
    id: UUID
    status: str
    integration_detail: object | None
    integration_execution: dict[str, object]


class DiscoveryEventCreate(BaseModel):
    event_type: Literal[
        "signal_observed",
        "context_observed",
        "workflow_identified",
        "workflow_testing",
        "workflow_approved",
        "workflow_rejected",
    ]
    site_id: UUID | None = None
    workflow_key: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
        pattern=r"^[a-zA-Z0-9_.:-]+$",
    )
    workflow_label: str | None = Field(default=None, min_length=1, max_length=255)
    source_ref: str | None = Field(default=None, min_length=1, max_length=255)
    dedupe_key: str | None = Field(default=None, min_length=1, max_length=255)
    confidence: float | None = Field(default=None, ge=0, le=1)
    evidence: dict[str, object] = Field(default_factory=dict)


class DiscoveryEventResponse(BaseModel):
    id: UUID
    organization_id: UUID
    site_id: UUID | None
    actor_user_id: UUID | None
    event_type: str
    workflow_key: str | None
    workflow_label: str | None
    source_type: str
    source_ref: str | None
    dedupe_key: str | None
    confidence: float | None
    evidence: dict[str, object]
    occurred_at: datetime
    created_at: datetime


class DiscoveryEventCreateResponse(BaseModel):
    event: DiscoveryEventResponse
    duplicate: bool


class DiscoveryWorkflowSummary(BaseModel):
    key: str
    label: str | None
    state: Literal["identified", "testing", "approved", "rejected"]
    latest_event_id: UUID
    latest_event_at: datetime


class DiscoveryEvidenceWorkflowCounts(BaseModel):
    identified: int = Field(ge=0)
    testing: int = Field(ge=0)
    approved: int = Field(ge=0)
    rejected: int = Field(ge=0)


class DiscoveryPhaseEvidence(BaseModel):
    listen: bool
    watch: bool
    learn: bool
    adapt: bool


class DiscoveryEvidenceSummaryResponse(BaseModel):
    event_count: int = Field(ge=0)
    signal_count: int = Field(ge=0)
    context_count: int = Field(ge=0)
    workflow_counts: DiscoveryEvidenceWorkflowCounts
    phase_evidence: DiscoveryPhaseEvidence
    latest_event_at: datetime | None
    workflows: list[DiscoveryWorkflowSummary]


class WorkspaceObservationResponse(BaseModel):
    id: UUID
