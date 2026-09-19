"""Risk-aware workflow selection for Satchy decisions."""

from __future__ import annotations

from .schemas import IntentResolution, SatchyIntent, WorkflowMode

_AUTO_COMPLETE = frozenset(
    {
        SatchyIntent.INFORMATION,
        SatchyIntent.QUESTION,
        SatchyIntent.LOG_OBSERVATION,
        SatchyIntent.SUMMARIZE,
        SatchyIntent.REPEAT,
        SatchyIntent.CORRECT_RECORD,
        SatchyIntent.MISSION_STATUS,
    }
)

_ALWAYS_CONFIRM = frozenset(
    {
        SatchyIntent.APPROVE_ACTION,
        SatchyIntent.REJECT_ACTION,
        SatchyIntent.CANCEL_ACTION,
        SatchyIntent.REQUEST_ACTION,
        SatchyIntent.REQUEST_MISSION,
        SatchyIntent.ABORT_MISSION,
    }
)


def resolve_workflow(
    intent: IntentResolution,
    *,
    missing_critical_context: list[str] | None = None,
    approval_required: bool = False,
    preauthorized: bool = False,
) -> WorkflowMode:
    """Prefer completion over dialogue while failing closed on material ambiguity."""

    if missing_critical_context:
        return WorkflowMode.CLARIFY
    if approval_required and not preauthorized:
        return WorkflowMode.CONFIRM
    if intent.intent in _ALWAYS_CONFIRM and not preauthorized:
        return WorkflowMode.CONFIRM
    if intent.intent in _AUTO_COMPLETE or preauthorized:
        return WorkflowMode.AUTO_COMPLETE
    return WorkflowMode.CLARIFY
