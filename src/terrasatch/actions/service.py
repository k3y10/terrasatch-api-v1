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
from terrasatch.config import Settings
from terrasatch.edge.models import EdgeCommand, EdgeDevice
from terrasatch.errors import (
    InvalidConfiguration,
    ResourceNotFound,
    TenantAccessDenied,
    TerraSatchError,
)
from terrasatch.identity.models import Team
from terrasatch.integrations.models import IntegrationDelivery
from terrasatch.integrations.runtime import (
    execute as execute_integration_capability,
    resolve_connection as resolve_integration_connection,
)
from terrasatch.outbound.models import OutboundStatus, OutboundTransmission
from terrasatch.radio.models import Callsign, RadioConversation, Transmission

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


def _authorize_approval(
    *,
    approval_source: str,
    approver_role: str,
    authorized_roles: set[str] | frozenset[str],
    approver_callsign_id: UUID | None = None,
    source_transmission_id: UUID | None = None,
) -> None:
    if approval_source not in {"console", "radio"}:
        raise InvalidConfiguration("Unsupported Satchy approval source")
    if approver_role.casefold() not in {item.casefold() for item in authorized_roles}:
        raise TenantAccessDenied("Approver role is not authorized for Satchy actions")
    if approval_source == "radio" and (
        approver_callsign_id is None or source_transmission_id is None
    ):
        raise InvalidConfiguration(
            "Radio approval requires an attributed callsign and source transmission"
        )


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
    _authorize_approval(
        approval_source=approval_source,
        approver_role=approver_role,
        authorized_roles=authorized_roles,
        approver_callsign_id=approver_callsign_id,
        source_transmission_id=source_transmission_id,
    )
    if ActionStatus(action.status) != ActionStatus.AWAITING_APPROVAL:
        raise InvalidConfiguration("Only actions awaiting approval can be approved")
    if edited_message is not None:
        if action.action_type == ActionType.GENERATE_REPORT.value:
            normalized = edited_message.strip()
        else:
            normalized = " ".join(edited_message.split())
        if not normalized:
            raise InvalidConfiguration("Approved action content cannot be empty")
        action.proposed_message = normalized
        structured = dict(action.structured_payload or {})
        if action.action_type == ActionType.NOTIFY_TEAM.value:
            structured["text"] = normalized
        elif action.action_type == ActionType.GENERATE_REPORT.value:
            structured["content"] = normalized
        action.structured_payload = structured

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
    approval_source: str = "console",
    approver_callsign_id: UUID | None = None,
    source_transmission_id: UUID | None = None,
    authorized_roles: set[str] | frozenset[str] | None = None,
) -> tuple[SatchyAction, ActionApproval]:
    """Reject an awaiting proposal without producing outbound work."""

    _authorize_approval(
        approval_source=approval_source,
        approver_role=approver_role,
        authorized_roles=authorized_roles or DEFAULT_AUTHORIZED_APPROVER_ROLES,
        approver_callsign_id=approver_callsign_id,
        source_transmission_id=source_transmission_id,
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
        approver_callsign_id=approver_callsign_id,
        approver_role=approver_role.casefold(),
        approval_source=approval_source,
        source_transmission_id=source_transmission_id,
        decision="rejected",
        notes=notes.strip() if notes and notes.strip() else None,
        created_at=now,
    )
    session.add(approval)
    await session.flush()
    return action, approval


_INTEGRATION_ACTION_CAPABILITIES = {
    ActionType.NOTIFY_TEAM.value: "notification.send",
    ActionType.GENERATE_REPORT.value: "document.create",
}


def _payload_uuid(payload: dict[str, object], key: str) -> UUID | None:
    raw = payload.get(key)
    if raw is None:
        return None
    if isinstance(raw, UUID):
        return raw
    if isinstance(raw, str):
        try:
            return UUID(raw)
        except ValueError as error:
            raise InvalidConfiguration(f"{key} must be a UUID") from error
    raise InvalidConfiguration(f"{key} must be a UUID")


def _integration_action_request(
    action: SatchyAction,
) -> tuple[str, dict[str, object], UUID | None, str]:
    capability = _INTEGRATION_ACTION_CAPABILITIES.get(action.action_type)
    if capability is None:
        raise InvalidConfiguration("This Satchy action does not use an integration capability")

    structured = dict(action.structured_payload or {})
    connection_id = _payload_uuid(structured, "integration_connection_id")
    workflow_key = structured.get("workflow_key")
    if workflow_key is None:
        workflow_key = f"satchy.action.{action.action_type}"
    if not isinstance(workflow_key, str) or not workflow_key.strip():
        raise InvalidConfiguration("workflow_key must be a non-empty string")

    if action.action_type == ActionType.NOTIFY_TEAM.value:
        text = action.proposed_message or structured.get("text") or structured.get("message")
        if not isinstance(text, str) or not text.strip():
            raise InvalidConfiguration("notify_team requires an approved message")
        return (
            capability,
            {"text": text.strip()},
            connection_id,
            workflow_key.strip(),
        )

    content = structured.get("content") or structured.get("report") or action.proposed_message
    if not isinstance(content, str) or not content.strip():
        raise InvalidConfiguration("generate_report requires report content")
    name = structured.get("name") or structured.get("filename")
    if name is None:
        name = f"satchy-report-{action.id}.md"
    mime_type = structured.get("mime_type", "text/markdown")
    if not isinstance(name, str) or not name.strip():
        raise InvalidConfiguration("generate_report requires a valid file name")
    if not isinstance(mime_type, str) or not mime_type.strip():
        raise InvalidConfiguration("generate_report requires a valid MIME type")
    return (
        capability,
        {
            "name": name.strip(),
            "content": content,
            "mime_type": mime_type.strip(),
        },
        connection_id,
        workflow_key.strip(),
    )


async def _integration_action_team_ids(
    session: AsyncSession,
    action: SatchyAction,
) -> tuple[UUID, ...]:
    team_ids: set[UUID] = set()
    structured = dict(action.structured_payload or {})
    explicit_team = _payload_uuid(structured, "team_id")
    if explicit_team is not None:
        team = await session.scalar(
            select(Team).where(
                Team.id == explicit_team,
                Team.organization_id == action.organization_id,
                Team.enabled.is_(True),
            )
        )
        if team is None:
            raise ResourceNotFound("Integration action team was not found")
        team_ids.add(team.id)

    source = await session.scalar(
        select(Transmission).where(
            Transmission.id == action.source_transmission_id,
            Transmission.organization_id == action.organization_id,
        )
    )
    if source is not None and source.speaker_callsign_id is not None:
        callsign = await session.scalar(
            select(Callsign).where(
                Callsign.id == source.speaker_callsign_id,
                Callsign.organization_id == action.organization_id,
            )
        )
        if callsign is not None and callsign.team_id is not None:
            team_ids.add(callsign.team_id)
    return tuple(sorted(team_ids, key=str))


async def execute_approved_integration_action(
    session: AsyncSession,
    settings: Settings,
    *,
    action: SatchyAction,
    approver_user_id: UUID | None,
) -> tuple[SatchyAction, IntegrationDelivery | None, str | None]:
    """Execute an approved Satchy integration action through capability grants."""

    if ActionStatus(action.status) != ActionStatus.APPROVED:
        raise InvalidConfiguration("Integration action must be approved before execution")

    try:
        capability, payload, connection_id, workflow_key = _integration_action_request(action)
        team_ids = await _integration_action_team_ids(session, action)
        connection = await resolve_integration_connection(
            session,
            organization_id=action.organization_id,
            user_id=approver_user_id,
            capability=capability,
            team_ids=team_ids,
            agent_key="satchy",
            workflow_key=workflow_key,
            connection_id=connection_id,
        )
    except (InvalidConfiguration, ResourceNotFound) as error:
        structured = dict(action.structured_payload or {})
        structured["integration_execution"] = {
            "status": "blocked",
            "detail": error.message,
        }
        action.structured_payload = structured
        await session.flush()
        return action, None, error.message

    now = datetime.now(UTC)
    transition_action(action, ActionStatus.QUEUED, now=now)
    transition_action(action, ActionStatus.EXECUTING, now=now)

    try:
        delivery = await execute_integration_capability(
            session,
            settings,
            organization_id=action.organization_id,
            user_id=approver_user_id,
            capability=capability,
            request_id=action.id,
            payload=payload,
            team_ids=team_ids,
            agent_key="satchy",
            workflow_key=workflow_key,
            connection_id=connection.id,
        )
    except TerraSatchError as error:
        transition_action(action, ActionStatus.FAILED)
        structured = dict(action.structured_payload or {})
        structured["integration_execution"] = {
            "status": "failed",
            "capability": capability,
            "detail": error.message,
        }
        action.structured_payload = structured
        await session.flush()
        return action, None, error.message

    target = (
        ActionStatus.COMPLETED
        if delivery.status == "delivered"
        else ActionStatus.FAILED
    )
    transition_action(action, target)
    structured = dict(action.structured_payload or {})
    structured["integration_execution"] = {
        "status": delivery.status,
        "capability": capability,
        "delivery_id": str(delivery.id),
    }
    if delivery.last_error:
        structured["integration_execution"]["detail"] = delivery.last_error
    action.structured_payload = structured
    await session.flush()
    return action, delivery, delivery.last_error


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