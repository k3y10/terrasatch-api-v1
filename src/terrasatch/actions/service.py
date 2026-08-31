"""Human approval and outbound queue orchestration for Satchy actions."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.actions.models import (
    ActionApproval,
    ActionStatus,
    ActionType,
    SatchyAction,
)
from terrasatch.actions.state import transition_action
from terrasatch.admin.ai_channel import ai_channel_config, rf_reply_policy_allows
from terrasatch.edge.models import EdgeCommand, EdgeDevice
from terrasatch.errors import InvalidConfiguration, ResourceNotFound, TenantAccessDenied
from terrasatch.outbound.models import OutboundStatus, OutboundTransmission
from terrasatch.radio.models import RadioConversation, Transmission

DEFAULT_AUTHORIZED_APPROVER_ROLES = frozenset({"owner", "admin", "operator"})


async def get_action(
    session: AsyncSession,
    *,
    organization_id: UUID,
    action_id: UUID,
    for_update: bool = False,
) -> SatchyAction:
    query = select(SatchyAction).where(
        SatchyAction.id == action_id,
        SatchyAction.organization_id == organization_id,
    )
    if for_update:
        query = query.with_for_update()
    action = await session.scalar(query)
    if action is None:
        raise ResourceNotFound("Satchy action was not found")
    return action


async def list_actions(
    session: AsyncSession,
    *,
    organization_id: UUID,
    limit: int = 100,
) -> list[SatchyAction]:
    return list(
        await session.scalars(
            select(SatchyAction)
            .where(SatchyAction.organization_id == organization_id)
            .order_by(SatchyAction.created_at.desc())
            .limit(limit)
        )
    )


def _authorize_console_approval(
    *,
    approval_source: str,
    approver_role: str,
    authorized_roles: set[str] | frozenset[str],
) -> None:
    if approval_source != "console":
        raise InvalidConfiguration("Only console approval can authorize execution in this release")
    if approver_role.casefold() not in {item.casefold() for item in authorized_roles}:
        raise TenantAccessDenied("Approver role is not authorized for Satchy actions")


async def approve_action(
    session: AsyncSession,
    *,
    organization_id: UUID,
    action_id: UUID,
    approver_role: str,
    approval_source: str = "console",
    approver_user_id: UUID | None = None,
    approver_callsign_id: UUID | None = None,
    source_transmission_id: UUID | None = None,
    notes: str | None = None,
    edited_message: str | None = None,
    authorized_roles: set[str] | frozenset[str] | None = None,
) -> tuple[SatchyAction, ActionApproval]:
    """Record one authorized human decision and advance only to approved."""

    action = await get_action(
        session,
        organization_id=organization_id,
        action_id=action_id,
        for_update=True,
    )
    if authorized_roles is None:
        device = await session.scalar(
            select(EdgeDevice)
            .where(
                EdgeDevice.organization_id == organization_id,
                EdgeDevice.site_id == action.site_id,
                EdgeDevice.enabled.is_(True),
            )
            .order_by(EdgeDevice.last_seen_at.desc(), EdgeDevice.created_at.desc())
            .limit(1)
        )
        configured_roles = (
            ai_channel_config(device).get("authorized_approver_roles") if device else None
        )
        authorized_roles = (
            {str(item) for item in configured_roles}
            if isinstance(configured_roles, list)
            else DEFAULT_AUTHORIZED_APPROVER_ROLES
        )
    _authorize_console_approval(
        approval_source=approval_source,
        approver_role=approver_role,
        authorized_roles=authorized_roles,
    )
    if ActionStatus(action.status) != ActionStatus.AWAITING_APPROVAL:
        raise InvalidConfiguration("Only actions awaiting approval can be approved")
    if edited_message is not None:
        normalized = " ".join(edited_message.split())
        if not normalized:
            raise InvalidConfiguration("Approved radio message cannot be empty")
        action.proposed_message = normalized

    now = datetime.now(UTC)
    transition_action(action, ActionStatus.APPROVED, now=now)
    approval = ActionApproval(
        action_id=action.id,
        organization_id=organization_id,
        approver_user_id=approver_user_id,
        approver_callsign_id=approver_callsign_id,
        approver_role=approver_role.casefold(),
        approval_source=approval_source,
        source_transmission_id=source_transmission_id,
        decision="approved",
        notes=notes.strip() if notes and notes.strip() else None,
        created_at=now,
    )
    session.add(approval)
    await session.flush()
    return action, approval


async def reject_action(
    session: AsyncSession,
    *,
    organization_id: UUID,
    action_id: UUID,
    approver_role: str,
    notes: str | None = None,
    approver_user_id: UUID | None = None,
) -> tuple[SatchyAction, ActionApproval]:
    """Reject an awaiting proposal without producing outbound work."""

    _authorize_console_approval(
        approval_source="console",
        approver_role=approver_role,
        authorized_roles=DEFAULT_AUTHORIZED_APPROVER_ROLES,
    )
    action = await get_action(
        session,
        organization_id=organization_id,
        action_id=action_id,
        for_update=True,
    )
    if ActionStatus(action.status) != ActionStatus.AWAITING_APPROVAL:
        raise InvalidConfiguration("Only actions awaiting approval can be rejected")
    now = datetime.now(UTC)
    transition_action(action, ActionStatus.REJECTED, now=now)
    approval = ActionApproval(
        action_id=action.id,
        organization_id=organization_id,
        approver_user_id=approver_user_id,
        approver_callsign_id=None,
        approver_role=approver_role.casefold(),
        approval_source="console",
        source_transmission_id=None,
        decision="rejected",
        notes=notes.strip() if notes and notes.strip() else None,
        created_at=now,
    )
    session.add(approval)
    await session.flush()
    return action, approval


async def _edge_for_action(session: AsyncSession, action: SatchyAction) -> EdgeDevice:
    device = await session.scalar(
        select(EdgeDevice)
        .where(
            EdgeDevice.organization_id == action.organization_id,
            EdgeDevice.site_id == action.site_id,
            EdgeDevice.enabled.is_(True),
        )
        .order_by(EdgeDevice.last_seen_at.desc(), EdgeDevice.created_at.desc())
        .limit(1)
    )
    if device is None:
        raise ResourceNotFound("No enabled Edge device is assigned to the action site")
    return device


async def queue_approved_action(
    session: AsyncSession,
    *,
    organization_id: UUID,
    action_id: UUID,
) -> tuple[OutboundTransmission, EdgeCommand]:
    """Create exactly one outbound intent/command after explicit approval."""

    action = await get_action(
        session,
        organization_id=organization_id,
        action_id=action_id,
        for_update=True,
    )
    existing = await session.scalar(
        select(OutboundTransmission).where(
            OutboundTransmission.organization_id == organization_id,
            OutboundTransmission.action_id == action.id,
        )
    )
    if existing is not None:
        command = await session.scalar(
            select(EdgeCommand).where(
                EdgeCommand.organization_id == organization_id,
                EdgeCommand.outbound_transmission_id == existing.id,
            )
        )
        if command is None:
            raise RuntimeError("Outbound transmission is missing its Edge command")
        return existing, command

    if ActionStatus(action.status) != ActionStatus.APPROVED:
        raise InvalidConfiguration("Action must be approved before it can be queued")
    if action.action_type != ActionType.REPLY_RADIO.value:
        raise InvalidConfiguration("This action type does not create an outbound radio command")
    if not action.proposed_message:
        raise InvalidConfiguration("Approved radio action is missing a message")

    device = await _edge_for_action(session, action)
    ai_policy = ai_channel_config(device)
    configured_route = str(ai_policy.get("reply_route", "dashboard"))
    if configured_route == "rf" and not rf_reply_policy_allows(device):
        raise InvalidConfiguration(
            "RF reply requires reported TX capability and explicit Edge/AI-channel TX policy"
        )
    reply_route = "rf" if configured_route == "rf" else "simulation"

    conversation = await session.scalar(
        select(RadioConversation).where(
            RadioConversation.id == action.conversation_id,
            RadioConversation.organization_id == organization_id,
        )
    )
    source = await session.scalar(
        select(Transmission).where(
            Transmission.id == action.source_transmission_id,
            Transmission.organization_id == organization_id,
        )
    )
    if conversation is None or source is None:
        raise ResourceNotFound("Action source conversation or transmission was not found")

    now = datetime.now(UTC)
    outbound = OutboundTransmission(
        organization_id=organization_id,
        site_id=action.site_id,
        edge_device_id=device.id,
        action_id=action.id,
        conversation_id=action.conversation_id,
        channel_id=conversation.channel_id,
        speaker_callsign="Satchy",
        recipient_callsign=source.speaker_text,
        text=action.proposed_message,
        priority="critical" if action.risk_level == "critical" else "normal",
        reply_route=reply_route,
        status=OutboundStatus.QUEUED.value,
        queued_at=now,
        expires_at=action.expires_at,
    )
    session.add(outbound)
    await session.flush()

    command = EdgeCommand(
        organization_id=organization_id,
        site_id=action.site_id,
        edge_device_id=device.id,
        outbound_transmission_id=outbound.id,
        command_type="radio_reply",
        payload={
            "outbound_transmission_id": str(outbound.id),
            "action_id": str(action.id),
            "conversation_id": str(action.conversation_id),
            "channel_id": str(conversation.channel_id) if conversation.channel_id else None,
            "speaker_callsign": outbound.speaker_callsign,
            "recipient_callsign": outbound.recipient_callsign,
            "text": outbound.text,
            "reply_route": reply_route,
            "simulate_only": reply_route != "rf",
        },
        priority=10 if outbound.priority == "critical" else 100,
        status="queued",
        expires_at=outbound.expires_at,
    )
    session.add(command)
    transition_action(action, ActionStatus.QUEUED, now=now)
    await session.flush()
    return outbound, command


async def approve_and_queue_action(
    session: AsyncSession,
    *,
    organization_id: UUID,
    action_id: UUID,
    approver_role: str,
    notes: str | None = None,
    edited_message: str | None = None,
) -> tuple[SatchyAction, ActionApproval, OutboundTransmission, EdgeCommand]:
    action, approval = await approve_action(
        session,
        organization_id=organization_id,
        action_id=action_id,
        approver_role=approver_role,
        notes=notes,
        edited_message=edited_message,
    )
    outbound, command = await queue_approved_action(
        session,
        organization_id=organization_id,
        action_id=action.id,
    )
    return action, approval, outbound, command
