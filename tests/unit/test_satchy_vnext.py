from __future__ import annotations

from uuid import uuid4

import pytest

from terrasatch.satchy_vnext.domains import infer_domain
from terrasatch.satchy_vnext.evals import EvalCase, evaluate_run, promotion_report
from terrasatch.satchy_vnext.policy import PolicyEngine
from terrasatch.satchy_vnext.providers import ModelRouter, ProviderRegistry, StaticModelProvider
from terrasatch.satchy_vnext.runtime import SatchyRuntime, SatchyRuntimeConfig
from terrasatch.satchy_vnext.schemas import (
    AgentRequest,
    Connectivity,
    ContextPacket,
    DomainProfile,
    EvidenceClass,
    EvidenceRef,
    ExecutionMode,
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


@pytest.mark.asyncio
async def test_offline_routing_keeps_local_provider() -> None:
    providers = ProviderRegistry()
    providers.register(StaticModelProvider(), priority=10)
    router = ModelRouter(providers)
    provider, route = router.select(
        task_type=TaskType.QUESTION,
        connectivity=Connectivity.OFFLINE,
        risk_level=__import__(
            "terrasatch.satchy_vnext.schemas", fromlist=["RiskLevel"]
        ).RiskLevel.LOW,
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
