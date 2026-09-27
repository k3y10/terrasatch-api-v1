"""Fail-closed policy boundary for Satchy vNext."""

from __future__ import annotations

from pydantic import BaseModel

from .schemas import (
    ContextPacket,
    ExecutionMode,
    ProposedAction,
    RiskLevel,
    ToolEffect,
)
from .tools import ToolSpec


class PolicyDecision(BaseModel):
    allowed: bool
    approval_required: bool
    risk_level: RiskLevel
    reason: str


class PolicyEngine:
    """Satchy may reason broadly but cannot silently gain execution authority."""

    def evaluate_tool(
        self,
        *,
        spec: ToolSpec,
        context: ContextPacket,
        mode: ExecutionMode,
    ) -> PolicyDecision:
        allowlist = context.policy_context.get("tool_allowlist")
        if isinstance(allowlist, list) and allowlist and spec.name not in allowlist:
            return PolicyDecision(
                allowed=False,
                approval_required=True,
                risk_level=spec.risk_level,
                reason="Tool is outside the authorized context allowlist.",
            )

        granted_scopes = context.policy_context.get("scopes", [])
        if not isinstance(granted_scopes, list):
            granted_scopes = []
        missing_scopes = [
            scope for scope in spec.required_scopes if scope not in granted_scopes
        ]
        if missing_scopes:
            return PolicyDecision(
                allowed=False,
                approval_required=True,
                risk_level=spec.risk_level,
                reason="Missing required tool scopes: " + ", ".join(missing_scopes),
            )

        if spec.domains and context.domain.value not in spec.domains:
            return PolicyDecision(
                allowed=False,
                approval_required=True,
                risk_level=spec.risk_level,
                reason="Tool is not authorized for the active domain profile.",
            )

        if spec.effect == ToolEffect.READ:
            return PolicyDecision(
                allowed=True,
                approval_required=False,
                risk_level=spec.risk_level,
                reason="Read-only tool is eligible within the authorized context.",
            )

        # Side effects are never executed by this runtime. ACTIVE still delegates to the
        # existing action/approval control plane after an authorized human decision.
        return PolicyDecision(
            allowed=False,
            approval_required=True,
            risk_level=spec.risk_level,
            reason=(
                f"{spec.effect.value} tools are proposal-only in Satchy vNext "
                f"(runtime mode={mode.value})."
            ),
        )

    def normalize_action(
        self,
        action: ProposedAction,
        *,
        context: ContextPacket,
    ) -> ProposedAction:
        _ = context
        # Consequential actions always remain approval-gated. The model cannot lower risk.
        requires_approval = action.approval_required or action.risk_level != RiskLevel.LOW
        if action.action_type.startswith(("notify.", "edge.", "mission.", "radio.")):
            requires_approval = True
        return action.model_copy(update={"approval_required": requires_approval})

    def validate_evidence_ids(
        self,
        evidence_ids: list[str],
        *,
        context: ContextPacket,
    ) -> tuple[list[str], list[str]]:
        allowed = context.evidence_ids
        valid = [item for item in evidence_ids if item in allowed]
        rejected = [item for item in evidence_ids if item not in allowed]
        return valid, rejected
