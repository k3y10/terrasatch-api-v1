from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from terrasatch.satchy.schemas import SatchyContext
from terrasatch.satchy_vnext.bridge import context_packet_from_current
from terrasatch.satchy_vnext.domains import infer_domain
from terrasatch.satchy_vnext.evals import EvalCase, evaluate_run, promotion_report
from terrasatch.satchy_vnext.impact import ImpactMeasurement, summarize_impact
from terrasatch.satchy_vnext.policy import PolicyEngine
from terrasatch.satchy_vnext.providers import ModelRouter, ProviderRegistry, StaticModelProvider
from terrasatch.satchy_vnext.quality import QualityIssueType, inspect_context_quality
from terrasatch.satchy_vnext.runtime import SatchyRuntime, SatchyRuntimeConfig
from terrasatch.satchy_vnext.schemas import (
    AgentRequest,
    Connectivity,
    ContextPacket,
    DomainProfile,
    EvidenceClass,
    EvidenceRef,
    ExecutionMode,
    RiskLevel,
    RunStatus,
    TaskType,
    ToolEffect,
)
from terrasatch.satchy_vnext.tools import ToolRegistry, ToolSpec


def _context(*, connectivity: Connectivity = Connectivity.ONLINE) -> ContextPacket:
    return ContextPacket(
        organization_id=uuid4(),
        site_id=uuid4(),
        connectivity=connectivity,
        evidence=[
            EvidenceRef(
                id="obs-1",
                evidence_class=EvidenceClass.OBSERVED,
                source_type="radio",
                summary="Natural avalanche observed on a northeast aspect.",
                confidence=0.93,
            )
        ],
    )


def test_domain_inference_is_field_specific() -> None:
    assert infer_domain("natural avalanche on a wind slab") == DomainProfile.AVY
    assert infer_domain("wildfire perimeter and smoke update") == DomainProfile.PYRO
    assert infer_domain("river gauge stage rising") == DomainProfile.HYDRO
    assert infer_domain("bridge asset telemetry outage") == DomainProfile.INFRA


@pytest.mark.asyncio
async def test_disabled_runtime_never_calls_model() -> None:
    providers = ProviderRegistry()
    providers.register(
        StaticModelProvider(
            {
                "answer": "should never run",
                "confidence": 1.0,
                "evidence_ids": [],
            }
        )
    )
    runtime = SatchyRuntime(
        config=SatchyRuntimeConfig(enabled=False, mode=ExecutionMode.SHADOW),
        router=ModelRouter(providers),
        tools=ToolRegistry(),
    )
    run = await runtime.run(
        AgentRequest(message="What happened?", context=_context())
    )
    assert run.status == RunStatus.DISABLED
    assert run.usage == []


@pytest.mark.asyncio
async def test_write_tool_is_only_proposed_and_never_executed() -> None:
    response = {
        "answer": "I can prepare a team notification for review.",
        "confidence": 0.91,
        "evidence_ids": ["obs-1"],
        "missing_context": [],
        "tool_requests": [
            {
                "name": "notify.team",
                "arguments": {"text": "Natural avalanche observed."},
                "reason": "Share the sourced observation with the team.",
                "evidence_ids": ["obs-1"],
            }
        ],
        "proposed_actions": [],
        "follow_up_required": False,
    }
    providers = ProviderRegistry()
    providers.register(StaticModelProvider(response), priority=0)

    async def must_not_run(_arguments, _context):
        await asyncio.sleep(0)
        raise AssertionError("external-write handler must never execute")

    tools = ToolRegistry()
    tools.register(
        ToolSpec(
            name="notify.team",
            description="Send an external team notification.",
            effect=ToolEffect.EXTERNAL_WRITE,
        ),
        must_not_run,
    )
    runtime = SatchyRuntime(
        config=SatchyRuntimeConfig(
            enabled=True,
            mode=ExecutionMode.SHADOW,
            refine_after_read_tools=False,
        ),
        router=ModelRouter(providers),
        tools=tools,
        policy=PolicyEngine(),
    )
    run = await runtime.run(
        AgentRequest(
            message="Notify the team.",
            context=_context(),
            task_type=TaskType.NOTIFY,
        )
    )
    assert run.status == RunStatus.COMPLETED
    assert len(run.proposed_actions) == 1
    assert run.proposed_actions[0].approval_required is True
    assert run.proposed_actions[0].action_type == "notify.team"


@pytest.mark.asyncio
async def test_unauthorized_evidence_is_removed_and_warned() -> None:
    providers = ProviderRegistry()
    providers.register(
        StaticModelProvider(
            {
                "answer": "A report exists.",
                "confidence": 0.99,
                "evidence_ids": ["invented-id"],
                "missing_context": [],
                "tool_requests": [],
                "proposed_actions": [],
                "follow_up_required": False,
            }
        ),
        priority=0,
    )
    runtime = SatchyRuntime(
        config=SatchyRuntimeConfig(
            enabled=True,
            mode=ExecutionMode.SHADOW,
            refine_after_read_tools=False,
        ),
        router=ModelRouter(providers),
        tools=ToolRegistry(),
    )
    run = await runtime.run(
        AgentRequest(message="Summarize.", context=_context(), task_type=TaskType.SUMMARIZE)
    )
    assert run.status == RunStatus.COMPLETED
    assert run.plan is not None
    assert run.plan.evidence_ids == []
    assert run.plan.confidence <= 0.35
    assert any("unauthorized evidence" in warning for warning in run.warnings)


def test_offline_routing_keeps_local_provider() -> None:
    providers = ProviderRegistry()
    providers.register(StaticModelProvider(), priority=10)
    router = ModelRouter(providers)
    provider, route = router.select(
        task_type=TaskType.QUESTION,
        connectivity=Connectivity.OFFLINE,
        risk_level=RiskLevel.LOW,
        prefer_local=True,
    )
    assert provider.local is True
    assert route.local is True


@pytest.mark.asyncio
async def test_eval_gate_rewards_grounding_and_approval() -> None:
    providers = ProviderRegistry()
    providers.register(
        StaticModelProvider(
            {
                "answer": "Natural avalanche observed.",
                "confidence": 0.95,
                "evidence_ids": ["obs-1"],
                "missing_context": [],
                "tool_requests": [],
                "proposed_actions": [],
                "follow_up_required": False,
            }
        ),
        priority=0,
    )
    runtime = SatchyRuntime(
        config=SatchyRuntimeConfig(
            enabled=True,
            mode=ExecutionMode.SHADOW,
            refine_after_read_tools=False,
        ),
        router=ModelRouter(providers),
        tools=ToolRegistry(),
    )
    run = await runtime.run(
        AgentRequest(
            message="Summarize the avalanche observation.",
            context=_context(),
            task_type=TaskType.SUMMARIZE,
            preferred_domain=DomainProfile.AVY,
        )
    )
    score = evaluate_run(
        run,
        EvalCase(
            name="grounded-avalanche-summary",
            expected_domain=DomainProfile.AVY,
            required_evidence_ids=["obs-1"],
        ),
    )
    assert score.grounding == 1.0
    assert score.action_safety == 1.0
    report = promotion_report([score])
    assert report.mean_grounding == 1.0


def test_context_quality_flags_same_location_fact_conflict_and_staleness() -> None:
    now = datetime.now(UTC)
    packet = ContextPacket(
        organization_id=uuid4(),
        site_id=uuid4(),
        evidence=[
            EvidenceRef(
                id="radio-1",
                evidence_class=EvidenceClass.OBSERVED,
                source_type="radio",
                summary="Road reported open.",
                facts={"road_status": "open"},
                location={"text": "Cardiff"},
                observed_at=now - timedelta(minutes=5),
            ),
            EvidenceRef(
                id="ops-2",
                evidence_class=EvidenceClass.OFFICIAL_PUBLISHED,
                source_type="official_notice",
                summary="Road reported closed.",
                facts={"road_status": "closed"},
                location={"text": "Cardiff"},
                observed_at=now - timedelta(hours=10),
            ),
        ],
    )
    report = inspect_context_quality(packet, now=now)
    assert report.contradiction_count == 1
    assert report.stale_count == 1
    assert any(
        issue.issue_type == QualityIssueType.CONTRADICTION
        for issue in report.issues
    )


def test_impact_summary_uses_measured_values_only() -> None:
    measurements = [
        ImpactMeasurement(
            workflow="shift_report",
            manual_seconds=900,
            assisted_seconds=240,
            accepted=True,
            edit_ratio=0.10,
            source_record_count=12,
        ),
        ImpactMeasurement(
            workflow="shift_report",
            manual_seconds=600,
            assisted_seconds=300,
            accepted=False,
            edit_ratio=0.40,
            source_record_count=8,
        ),
    ]
    summary = summarize_impact(measurements)
    assert summary.measurement_count == 2
    assert summary.measured_minutes_saved == 16.0
    assert summary.acceptance_rate == 0.5
    assert summary.mean_edit_ratio == 0.25
    assert summary.source_record_count == 20


def test_current_satchy_context_bridge_preserves_source_classification() -> None:
    organization_id = uuid4()
    site_id = uuid4()
    current = SatchyContext(
        organization_id=organization_id,
        site_id=site_id,
        evidence=[
            {
                "id": "tx-1",
                "type": "source_transmission",
                "summary": "Control 2 reports no avalanche activity.",
                "confidence": 1.0,
                "location": "Cardiff Bowl",
                "created_at": "2026-09-27T16:00:00+00:00",
            },
            {
                "id": "event-1",
                "type": "observation",
                "summary": "No avalanche activity observed.",
                "confidence": 0.92,
                "location": "Cardiff Bowl",
                "created_at": "2026-09-27T16:00:01+00:00",
            },
        ],
    )
    packet = context_packet_from_current(current, domain=DomainProfile.AVY)
    assert packet.organization_id == organization_id
    assert packet.site_id == site_id
    assert packet.domain == DomainProfile.AVY
    assert packet.evidence[0].evidence_class == EvidenceClass.OBSERVED
    assert packet.evidence[1].evidence_class == EvidenceClass.DERIVED
    assert packet.policy_context["proposal_only"] is True
