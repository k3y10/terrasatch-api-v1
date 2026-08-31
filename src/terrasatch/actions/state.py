"""Deterministic Satchy action state machine."""

from __future__ import annotations

from datetime import UTC, datetime

from terrasatch.actions.models import ActionStatus, SatchyAction
from terrasatch.errors import InvalidConfiguration

_TRANSITIONS: dict[ActionStatus, frozenset[ActionStatus]] = {
    ActionStatus.PROPOSED: frozenset({ActionStatus.AWAITING_APPROVAL, ActionStatus.CANCELLED}),
    ActionStatus.AWAITING_APPROVAL: frozenset(
        {
            ActionStatus.APPROVED,
            ActionStatus.REJECTED,
            ActionStatus.EXPIRED,
            ActionStatus.CANCELLED,
        }
    ),
    ActionStatus.APPROVED: frozenset(
        {ActionStatus.QUEUED, ActionStatus.EXPIRED, ActionStatus.CANCELLED}
    ),
    ActionStatus.QUEUED: frozenset(
        {
            ActionStatus.EXECUTING,
            ActionStatus.FAILED,
            ActionStatus.EXPIRED,
            ActionStatus.CANCELLED,
        }
    ),
    ActionStatus.EXECUTING: frozenset(
        {ActionStatus.COMPLETED, ActionStatus.FAILED, ActionStatus.CANCELLED}
    ),
    ActionStatus.COMPLETED: frozenset(),
    ActionStatus.REJECTED: frozenset(),
    ActionStatus.EXPIRED: frozenset(),
    ActionStatus.FAILED: frozenset(),
    ActionStatus.CANCELLED: frozenset(),
}


def transition_action(
    action: SatchyAction,
    target: ActionStatus,
    *,
    now: datetime | None = None,
) -> None:
    """Apply one allowed edge; callers cannot skip approval or queue states."""

    current = ActionStatus(action.status)
    if target not in _TRANSITIONS[current]:
        raise InvalidConfiguration(
            f"Invalid Satchy action transition: {current.value} -> {target.value}"
        )
    changed_at = now or datetime.now(UTC)
    expires_at = action.expires_at
    if expires_at is not None and expires_at.utcoffset() is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at is not None and expires_at <= changed_at:
        if target != ActionStatus.EXPIRED:
            raise InvalidConfiguration("Expired Satchy actions cannot advance")
    action.status = target.value
    if target == ActionStatus.APPROVED:
        action.approved_at = changed_at
    if target in {ActionStatus.COMPLETED, ActionStatus.FAILED}:
        action.executed_at = changed_at
