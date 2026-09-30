"""Persistent, inspectable Satchy workspace runs.

Run steps record operational activity, tool/source use, and approval state only.
They must never contain hidden chain-of-thought or model scratchpad content.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.satchy.models import SatchyRun, SatchyRunStep


async def get_or_create_run(
    session: AsyncSession,
    *,
    organization_id: UUID,
    site_id: UUID,
    user_id: UUID,
    request_id: UUID,
    input_text: str,
    objective: str | None,
    run_metadata: dict[str, object] | None = None,
) -> tuple[SatchyRun, bool]:
    existing = await session.scalar(
        select(SatchyRun).where(
            SatchyRun.organization_id == organization_id,
            SatchyRun.user_id == user_id,
            SatchyRun.request_id == request_id,
        )
    )
    if existing is not None:
        return existing, False

    run = SatchyRun(
        organization_id=organization_id,
        site_id=site_id,
        user_id=user_id,
        request_id=request_id,
        input_text=input_text,
        objective=objective,
        status="running",
        run_metadata=dict(run_metadata or {}),
    )
    session.add(run)
    await session.flush()
    return run, True


async def append_run_step(
    session: AsyncSession,
    *,
    run: SatchyRun,
    step_type: str,
    status: str,
    label: str,
    detail: dict[str, object] | None = None,
    source_refs: list[dict[str, object]] | None = None,
    action_id: UUID | None = None,
    completed: bool = True,
) -> SatchyRunStep:
    current_sequence = await session.scalar(
        select(func.max(SatchyRunStep.sequence)).where(SatchyRunStep.run_id == run.id)
    )
    step = SatchyRunStep(
        organization_id=run.organization_id,
        run_id=run.id,
        action_id=action_id,
        sequence=int(current_sequence or 0) + 1,
        step_type=step_type,
        status=status,
        label=label[:255],
        detail=dict(detail or {}),
        source_refs=list(source_refs or []),
        completed_at=datetime.now(UTC) if completed else None,
    )
    session.add(step)
    await session.flush()
    return step


def finish_run(
    run: SatchyRun,
    *,
    status: str,
    response_text: str | None = None,
    model: str | None = None,
) -> None:
    run.status = status
    if response_text is not None:
        run.response_text = response_text
    if model is not None:
        run.model = model
    if status in {"completed", "failed", "needs_input"}:
        run.completed_at = datetime.now(UTC)
    else:
        run.completed_at = None


async def run_steps(session: AsyncSession, *, run_id: UUID) -> list[SatchyRunStep]:
    return list(
        await session.scalars(
            select(SatchyRunStep)
            .where(SatchyRunStep.run_id == run_id)
            .order_by(SatchyRunStep.sequence)
        )
    )


async def sync_action_review(
    session: AsyncSession,
    *,
    organization_id: UUID,
    action_id: UUID,
    decision: str,
    action_status: str,
    integration_execution: dict[str, object] | None = None,
) -> None:
    """Reflect a human action decision back into the owning run activity."""

    step = await session.scalar(
        select(SatchyRunStep)
        .where(
            SatchyRunStep.organization_id == organization_id,
            SatchyRunStep.action_id == action_id,
        )
        .order_by(SatchyRunStep.sequence.desc())
        .limit(1)
    )
    if step is None:
        return

    now = datetime.now(UTC)
    execution = dict(integration_execution or {})
    step.status = "completed" if decision == "approve" else "rejected"
    step.completed_at = now
    step.detail = {
        **dict(step.detail or {}),
        "decision": decision,
        "action_status": action_status,
        "execution_status": execution.get("status"),
    }

    run = await session.get(SatchyRun, step.run_id)
    if run is None:
        return

    execution_status = execution.get("status")
    run_status = (
        "failed"
        if decision == "approve" and execution_status in {"blocked", "failed"}
        else "completed"
    )
    finish_run(run, status=run_status)
    await append_run_step(
        session,
        run=run,
        step_type="review",
        status="completed" if decision == "approve" else "rejected",
        label="Action approved" if decision == "approve" else "Action rejected",
        detail={
            "action_status": action_status,
            "execution_status": execution_status,
        },
        action_id=action_id,
    )


def step_payload(step: SatchyRunStep) -> dict[str, object]:
    return {
        "id": str(step.id),
        "sequence": step.sequence,
        "type": step.step_type,
        "status": step.status,
        "label": step.label,
        "detail": dict(step.detail or {}),
        "source_refs": list(step.source_refs or []),
        "action_id": str(step.action_id) if step.action_id else None,
        "created_at": step.created_at,
        "completed_at": step.completed_at,
    }


async def run_payload(session: AsyncSession, *, run: SatchyRun) -> dict[str, object]:
    steps = await run_steps(session, run_id=run.id)
    return {
        "id": str(run.id),
        "request_id": str(run.request_id),
        "organization_id": str(run.organization_id),
        "site_id": str(run.site_id),
        "user_id": str(run.user_id) if run.user_id else None,
        "objective": run.objective,
        "input_text": run.input_text,
        "response_text": run.response_text,
        "model": run.model,
        "status": run.status,
        "metadata": dict(run.run_metadata or {}),
        "created_at": run.created_at,
        "updated_at": run.updated_at,
        "completed_at": run.completed_at,
        "steps": [step_payload(step) for step in steps],
    }
