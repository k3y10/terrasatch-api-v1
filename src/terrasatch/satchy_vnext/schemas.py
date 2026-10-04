"""Isolated Satchy vNext contracts.

Nothing in production imports this package. These contracts intentionally model the future
agent boundary without changing the current Satchy control plane.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator


def utcnow() -> datetime:
    return datetime.now(UTC)


class ExecutionMode(StrEnum):
    OFF = "off"
    SHADOW = "shadow"
    SANDBOX = "sandbox"
    CANARY = "canary"
    ACTIVE = "active"


class RunStatus(StrEnum):
    DISABLED = "disabled"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


class DomainProfile(StrEnum):
    GENERAL = "general"
    AVY = "avy"
    PYRO = "pyro"
    HYDRO = "hydro"
    GEO = "geo"
    INFRA = "infra"


class EvidenceClass(StrEnum):
    OBSERVED = "observed"
    OFFICIAL_PUBLISHED = "official_published"
    MODELED = "modeled"
    DERIVED = "derived"
    USER_PROVIDED = "user_provided"
    AI_INTERPRETED = "ai_interpreted"


class Sensitivity(StrEnum):
    PUBLIC = "public"
    ORGANIZATION = "organization"
    RESTRICTED = "restricted"


class Connectivity(StrEnum):
    ONLINE = "online"
    DEGRADED = "degraded"
    OFFLINE = "offline"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ToolEffect(StrEnum):
    READ = "read"
    PROPOSE_WRITE = "propose_write"
    EXTERNAL_WRITE = "external_write"
    PHYSICAL = "physical"


class ToolStatus(StrEnum):
    COMPLETED = "completed"
    PROPOSED = "proposed"
    BLOCKED = "blocked"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


class TaskType(StrEnum):
    QUESTION = "question"
    SUMMARIZE = "summarize"
    EXTRACT = "extract"
    ANALYZE = "analyze"
    PLAN = "plan"
    REPORT = "report"
    NOTIFY = "notify"
    COMMAND = "command"


class ClaimType(StrEnum):
    FACT = "fact"
    INFERENCE = "inference"
    RECOMMENDATION = "recommendation"
    PROCESS = "process"


class EvidenceRef(BaseModel):
    id: str = Field(min_length=1, max_length=255)
    evidence_class: EvidenceClass
    source_type: str = Field(min_length=1, max_length=128)
    summary: str = Field(min_length=1, max_length=4000)
    facts: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=1.0, ge=0, le=1)
    sensitivity: Sensitivity = Sensitivity.ORGANIZATION
    source_uri: str | None = Field(default=None, max_length=2000)
    observed_at: datetime | None = None
    location: dict[str, Any] = Field(default_factory=dict)


class ContextPacket(BaseModel):
    """The only operational context a vNext model may treat as authorized input."""

    packet_id: UUID = Field(default_factory=uuid4)
    organization_id: UUID
    site_id: UUID
    user_id: UUID | None = None
    team_id: UUID | None = None
    incident_id: UUID | None = None
    objective: str | None = Field(default=None, max_length=2000)
    domain: DomainProfile = DomainProfile.GENERAL
    connectivity: Connectivity = Connectivity.ONLINE
    evidence: list[EvidenceRef] = Field(default_factory=list, max_length=128)
    spatial_context: dict[str, Any] = Field(default_factory=dict)
    environmental_context: dict[str, Any] = Field(default_factory=dict)
    operational_context: dict[str, Any] = Field(default_factory=dict)
    user_preferences: dict[str, Any] = Field(default_factory=dict)
    policy_context: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow)

    @model_validator(mode="after")
    def evidence_ids_are_unique(self):
        ids = [item.id for item in self.evidence]
        if len(ids) != len(set(ids)):
            raise ValueError("ContextPacket evidence IDs must be unique")
        return self

    @property
    def evidence_ids(self) -> set[str]:
        return {item.id for item in self.evidence}


class AgentRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20000)
    context: ContextPacket
    task_type: TaskType = TaskType.QUESTION
    preferred_domain: DomainProfile | None = None
    prefer_local_model: bool = True
    request_id: UUID = Field(default_factory=uuid4)


class ToolRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    arguments: dict[str, Any] = Field(default_factory=dict)
    reason: str = Field(min_length=1, max_length=1000)
    evidence_ids: list[str] = Field(default_factory=list, max_length=64)


class ProposedAction(BaseModel):
    action_type: str = Field(min_length=1, max_length=128)
    summary: str = Field(min_length=1, max_length=2000)
    payload: dict[str, Any] = Field(default_factory=dict)
    risk_level: RiskLevel = RiskLevel.MEDIUM
    approval_required: bool = True
    evidence_ids: list[str] = Field(default_factory=list, max_length=64)
    reversible: bool = False
    policy_reason: str | None = Field(default=None, max_length=2000)


class GroundedClaim(BaseModel):
    claim_type: ClaimType
    text: str = Field(min_length=1, max_length=4000)
    confidence: float = Field(ge=0, le=1)
    evidence_ids: list[str] = Field(default_factory=list, max_length=64)

    @model_validator(mode="after")
    def factual_claim_requires_evidence(self):
        if self.claim_type == ClaimType.FACT and not self.evidence_ids:
            raise ValueError("Factual claims require at least one evidence ID")
        return self


class AgentPlan(BaseModel):
    answer: str = Field(min_length=1, max_length=12000)
    confidence: float = Field(ge=0, le=1)
    claims: list[GroundedClaim] = Field(max_length=64)
    evidence_ids: list[str] = Field(default_factory=list, max_length=64)
    missing_context: list[str] = Field(default_factory=list, max_length=32)
    tool_requests: list[ToolRequest] = Field(default_factory=list, max_length=16)
    proposed_actions: list[ProposedAction] = Field(default_factory=list, max_length=16)
    follow_up_required: bool = False


class ToolResult(BaseModel):
    tool_name: str
    status: ToolStatus
    content: dict[str, Any] = Field(default_factory=dict)
    evidence: list[EvidenceRef] = Field(default_factory=list, max_length=64)
    proposed_action: ProposedAction | None = None
    error: str | None = Field(default=None, max_length=2000)


class ModelUsage(BaseModel):
    provider: str
    model: str
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    latency_ms: int | None = Field(default=None, ge=0)
    estimated_cost_usd: float | None = Field(default=None, ge=0)


class ModelRoute(BaseModel):
    provider: str
    model: str
    reason: str
    local: bool
    capabilities: list[str] = Field(default_factory=list)


class AgentRun(BaseModel):
    run_id: UUID = Field(default_factory=uuid4)
    request_id: UUID
    status: RunStatus
    mode: ExecutionMode
    domain: DomainProfile
    request: AgentRequest
    route: ModelRoute | None = None
    plan: AgentPlan | None = None
    tool_results: list[ToolResult] = Field(default_factory=list)
    proposed_actions: list[ProposedAction] = Field(default_factory=list)
    usage: list[ModelUsage] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=utcnow)
    completed_at: datetime | None = None
