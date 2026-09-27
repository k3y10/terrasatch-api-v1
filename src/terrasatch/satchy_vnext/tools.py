"""Typed tool registry for Satchy vNext.

The runtime executes read-only tools only. Any tool capable of changing an external or physical
system becomes a ProposedAction for the existing TerraSatch approval/execution control plane.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from .schemas import (
    ContextPacket,
    EvidenceRef,
    ProposedAction,
    RiskLevel,
    ToolEffect,
    ToolResult,
    ToolStatus,
)


class ToolSpec(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str = Field(min_length=1, max_length=2000)
    effect: ToolEffect
    risk_level: RiskLevel = RiskLevel.LOW
    arguments_schema: dict[str, Any] = Field(default_factory=dict)
    required_scopes: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)


ToolHandler = Callable[[dict[str, Any], ContextPacket], Awaitable[dict[str, Any]]]


@dataclass(slots=True)
class RegisteredTool:
    spec: ToolSpec
    handler: ToolHandler | None = None


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, RegisteredTool] = {}

    def register(self, spec: ToolSpec, handler: ToolHandler | None = None) -> None:
        if spec.name in self._tools:
            raise ValueError(f"Tool already registered: {spec.name}")
        self._tools[spec.name] = RegisteredTool(spec=spec, handler=handler)

    def get(self, name: str) -> RegisteredTool | None:
        return self._tools.get(name)

    def specs(self) -> list[ToolSpec]:
        return [self._tools[name].spec for name in sorted(self._tools)]

    async def run_read(
        self,
        *,
        name: str,
        arguments: dict[str, Any],
        context: ContextPacket,
    ) -> ToolResult:
        registered = self.get(name)
        if registered is None:
            return ToolResult(
                tool_name=name,
                status=ToolStatus.UNAVAILABLE,
                error="Tool is not registered.",
            )
        if registered.spec.effect != ToolEffect.READ:
            return ToolResult(
                tool_name=name,
                status=ToolStatus.PROPOSED,
                proposed_action=ProposedAction(
                    action_type=name,
                    summary=f"Satchy proposed {registered.spec.description}",
                    payload=dict(arguments),
                    risk_level=registered.spec.risk_level,
                    approval_required=True,
                ),
            )
        if registered.handler is None:
            return ToolResult(
                tool_name=name,
                status=ToolStatus.UNAVAILABLE,
                error="Read tool has no sandbox handler.",
            )
        try:
            raw = await registered.handler(arguments, context)
        except Exception as exc:  # tool isolation boundary
            return ToolResult(
                tool_name=name,
                status=ToolStatus.FAILED,
                error=f"{type(exc).__name__}: {exc}",
            )

        evidence_raw = raw.pop("evidence", []) if isinstance(raw, dict) else []
        evidence: list[EvidenceRef] = []
        for item in evidence_raw if isinstance(evidence_raw, list) else []:
            evidence.append(item if isinstance(item, EvidenceRef) else EvidenceRef.model_validate(item))
        return ToolResult(
            tool_name=name,
            status=ToolStatus.COMPLETED,
            content=raw if isinstance(raw, dict) else {"value": raw},
            evidence=evidence,
        )


def default_tool_specs() -> list[ToolSpec]:
    """Contracts only; production adapters are intentionally not attached."""

    return [
        ToolSpec(
            name="echo.search_signals",
            description="Search authorized EchoSatch radio, voice, and field-message records.",
            effect=ToolEffect.READ,
            arguments_schema={"type": "object", "properties": {"query": {"type": "string"}}},
        ),
        ToolSpec(
            name="grid.resolve_context",
            description="Resolve authorized GridSatch terrain, location, and spatial context.",
            effect=ToolEffect.READ,
            arguments_schema={
                "type": "object",
                "properties": {
                    "location_text": {"type": "string"},
                    "latitude": {"type": "number"},
                    "longitude": {"type": "number"},
                },
            },
        ),
        ToolSpec(
            name="core.explain_derivation",
            description="Explain a CoreSatch derived value and its source lineage.",
            effect=ToolEffect.READ,
        ),
        ToolSpec(
            name="quak.authorize",
            description="Check QuakSatch access policy without changing authorization state.",
            effect=ToolEffect.READ,
        ),
        ToolSpec(
            name="workspace.generate_report",
            description="Create a proposed operational report for human review.",
            effect=ToolEffect.PROPOSE_WRITE,
            risk_level=RiskLevel.MEDIUM,
        ),
        ToolSpec(
            name="notify.team",
            description="Send an external team notification through an approved integration.",
            effect=ToolEffect.EXTERNAL_WRITE,
            risk_level=RiskLevel.HIGH,
        ),
        ToolSpec(
            name="edge.command",
            description="Request a command on an authorized EdgeSatch field asset.",
            effect=ToolEffect.PHYSICAL,
            risk_level=RiskLevel.CRITICAL,
        ),
    ]
