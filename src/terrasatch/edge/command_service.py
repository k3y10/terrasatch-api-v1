"""Device-bound Edge command delivery and idempotent acknowledgement lifecycle."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.actions.models import ActionStatus, SatchyAction
from terrasatch.actions.state import transition_action
from terrasatch.admin.ai_channel import rf_reply_policy_allows
from terrasatch.edge.models import EdgeCommand
from terrasatch.edge.service import get_device_for_api_key
from terrasatch.errors import InvalidConfiguration, ResourceNotFound
from terrasatch.outbound.models import OutboundStatus, OutboundTransmission


async def _owned_command(
    session: AsyncSession,
    *,
    organization_id: UUID,
    api_key_id: UUID,
    command_id: UUID,
    for_update: bool = False,
) -> EdgeCommand:
    device = await get_device_for_api_key(
        session,
        organization_id=organization_id,
        api_key_id=api_key_id,
    )
    query = select(EdgeCommand).where(
        EdgeCommand.id == command_id,
        EdgeCommand.organization_id == organization_id,
        EdgeCommand.site_id == device.site_id,
        EdgeCommand.edge_device_id == device.id,
    )
    if for_update:
        query = query.with_for_update()
    command = await session.scalar(query)
    if command is None:
        raise ResourceNotFound("Edge command was not found for this device")
    return command


async def _linked_records(
    session: AsyncSession,
    *,
    command: EdgeCommand,
) -> tuple[OutboundTransmission | None, SatchyAction | None]:
    if command.outbound_transmission_id is None:
        return None, None
    outbound = await session.scalar(
        select(OutboundTransmission).where(
            OutboundTransmission.id == command.outbound_transmission_id,
            OutboundTransmission.organization_id == command.organization_id,
            OutboundTransmission.site_id == command.site_id,
            OutboundTransmission.edge_device_id == command.edge_device_id,
        )
    )
    if outbound is None:
        raise RuntimeError("Edge command is missing its outbound transmission")
    action = await session.scalar(
        select(SatchyAction).where(
            SatchyAction.id == outbound.action_id,
            SatchyAction.organization_id == command.organization_id,
            SatchyAction.site_id == command.site_id,
        )
    )
    if action is None:
        raise RuntimeError("Outbound transmission is missing its Satchy action")
    return outbound, action


async def _expire_command(session: AsyncSession, command: EdgeCommand, now: datetime) -> None:
    command.status = "expired"
    outbound, action = await _linked_records(session, command=command)
    if outbound is not None and outbound.status not in {
        OutboundStatus.SIMULATED.value,
        OutboundStatus.TRANSMITTED.value,
    }:
        outbound.status = OutboundStatus.EXPIRED.value
    if action is not None and ActionStatus(action.status) in {
        ActionStatus.APPROVED,
        ActionStatus.QUEUED,
    }:
        transition_action(action, ActionStatus.EXPIRED, now=now)


def _deadline_passed(value: datetime | None, now: datetime) -> bool:
    if value is None:
        return False
    if value.utcoffset() is None:
        value = value.replace(tzinfo=UTC)
    return value <= now


def _ensure_not_expired(command: EdgeCommand, now: datetime) -> None:
    if command.status == "expired" or _deadline_passed(command.expires_at, now):
        raise InvalidConfiguration("Expired Edge commands cannot execute")


async def list_device_commands(
    session: AsyncSession,
    *,
    organization_id: UUID,
    api_key_id: UUID,
    limit: int = 50,
) -> list[EdgeCommand]:
    """Return only work assigned to the authenticated physical Edge identity."""

    device = await get_device_for_api_key(
        session,
        organization_id=organization_id,
        api_key_id=api_key_id,
    )
    now = datetime.now(UTC)
    commands = list(
        await session.scalars(
            select(EdgeCommand)
            .where(
                EdgeCommand.organization_id == organization_id,
                EdgeCommand.site_id == device.site_id,
                EdgeCommand.edge_device_id == device.id,
                # Keep acknowledged work visible until Edge reports a terminal result.
                # This lets a device recover after it ACKs successfully but loses the
                # network response while posting the result.
                EdgeCommand.status.in_(("queued", "dispatched", "acknowledged")),
            )
            .order_by(EdgeCommand.priority, EdgeCommand.created_at)
            .limit(limit)
        )
    )
    available: list[EdgeCommand] = []
    for command in commands:
        if command.status != "acknowledged" and _deadline_passed(command.expires_at, now):
            await _expire_command(session, command, now)
            continue
        if command.status == "queued":
            command.status = "dispatched"
            outbound, _ = await _linked_records(session, command=command)
            if outbound is not None and outbound.status == OutboundStatus.QUEUED.value:
                outbound.status = OutboundStatus.DISPATCHED.value
        available.append(command)
    await session.flush()
    return available


async def acknowledge_command(
    session: AsyncSession,
    *,
    organization_id: UUID,
    api_key_id: UUID,
    command_id: UUID,
) -> EdgeCommand:
    """Idempotently record that the assigned Edge received the command."""

    command = await _owned_command(
        session,
        organization_id=organization_id,
        api_key_id=api_key_id,
        command_id=command_id,
        for_update=True,
    )
    now = datetime.now(UTC)
    _ensure_not_expired(command, now)
    if command.status in {"acknowledged", "completed"}:
        return command
    if command.status not in {"queued", "dispatched"}:
        raise InvalidConfiguration(
            f"Edge command in status '{command.status}' cannot be acknowledged"
        )

    if (command.payload or {}).get("reply_route") == "rf":
        device = await get_device_for_api_key(
            session, organization_id=organization_id, api_key_id=api_key_id,
        )
        if not rf_reply_policy_allows(device):
            raise InvalidConfiguration("RF reply policy was revoked before acknowledgement")

    command.status = "acknowledged"
    command.acknowledged_at = command.acknowledged_at or now
    outbound, action = await _linked_records(session, command=command)
    if outbound is not None and outbound.status in {
        OutboundStatus.QUEUED.value,
        OutboundStatus.DISPATCHED.value,
    }:
        outbound.status = OutboundStatus.EDGE_RECEIVED.value
        outbound.edge_received_at = outbound.edge_received_at or now
    if action is not None and ActionStatus(action.status) == ActionStatus.QUEUED:
        transition_action(action, ActionStatus.EXECUTING, now=now)
    await session.flush()
    return command


async def complete_command(
    session: AsyncSession,
    *,
    organization_id: UUID,
    api_key_id: UUID,
    command_id: UUID,
    result: str,
    detail: str | None = None,
) -> EdgeCommand:
    """Accept the initial simulated result or a failure exactly once."""

    command = await _owned_command(
        session,
        organization_id=organization_id,
        api_key_id=api_key_id,
        command_id=command_id,
        for_update=True,
    )
    now = datetime.now(UTC)
    if result not in {"simulated", "transmitted", "failed"}:
        raise InvalidConfiguration("Unsupported Edge command result")
    # A result is evidence about an already acknowledged operation. Accept late
    # results and identical retries; expiration must never force an RF replay.
    if command.status in {"completed", "failed"}:
        previous = str((command.payload or {}).get("result", "simulated"))
        if previous != result:
            raise InvalidConfiguration("Completed Edge command result cannot be changed")
        return command
    if command.status != "acknowledged":
        raise InvalidConfiguration("Edge command must be acknowledged before reporting a result")

    outbound, action = await _linked_records(session, command=command)
    payload = dict(command.payload or {})
    if result == "transmitted" and (
        command.command_type != "radio_reply"
        or payload.get("simulate_only") is not False
        or payload.get("reply_route") != "rf"
        or outbound is None or outbound.reply_route != "rf"
        or action is None or ActionStatus(action.status) != ActionStatus.EXECUTING
    ):
        raise InvalidConfiguration("Only acknowledged approved RF actions can report transmitted")
    if result == "simulated" and payload.get("simulate_only") is not True:
        raise InvalidConfiguration("RF execution cannot be reported as simulated")
    payload["result"] = result
    if detail:
        payload["result_detail"] = detail[:2000]
    command.payload = payload
    command.completed_at = now

    if result in {"simulated", "transmitted"}:
        command.status = "completed"
        if outbound is not None:
            outbound.status = result
            if result == "transmitted":
                outbound.transmitted_at = now
        if action is not None and ActionStatus(action.status) == ActionStatus.EXECUTING:
            transition_action(action, ActionStatus.COMPLETED, now=now)
    else:
        command.status = "failed"
        if outbound is not None:
            outbound.status = OutboundStatus.FAILED.value
            outbound.failed_at = now
        if action is not None and ActionStatus(action.status) == ActionStatus.EXECUTING:
            transition_action(action, ActionStatus.FAILED, now=now)
    await session.flush()
    return command

