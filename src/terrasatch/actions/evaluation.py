"""Structured Satchy evaluation around inbound radio context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.actions.models import ActionStatus, ActionType, SatchyAction, SatchyEvaluation
from terrasatch.actions.service import approve_action, queue_approved_action, reject_action
from terrasatch.actions.state import transition_action
from terrasatch.edge.models import EdgeDevice
from terrasatch.errors import InvalidConfiguration, ResourceNotFound
from terrasatch.organizations.models import OrganizationOperationalProfile
from terrasatch.organizations.profiles import get_operational_profile
from terrasatch.radio.conversations import associate_transmission
from terrasatch.radio.models import Callsign, OperationalEvent, RadioConversation, Transmission
from terrasatch.satchy.assets import create_mission_plan, queue_field_mission
from terrasatch.satchy.intents import resolve_intent
from terrasatch.satchy.radio import mission_ready, observation_logged, radio_prefix
from terrasatch.satchy.schemas import SatchyIntent

_DEFAULT_POLICY: dict[str, object] = {
    "response_mode": "suggest",
    "allowed_action_types": [item.value for item in ActionType],
    "conversation_timeout_seconds": 300,
    "emergency_detection_enabled": True,
    "emergency_auto_broadcast": False,
    "radio_approval_enabled": False,
    "authorized_approver_callsigns": [],
}
_DEFAULT_EMERGENCY_TERMS = {"emergency", "mayday", "broken leg", "serious injury", "help"}


@dataclass(frozen=True, slots=True)
class EvaluationOutcome:
    conversation: RadioConversation
    evaluation: SatchyEvaluation
    action: SatchyAction | None


async def _policy_for_site(
    session: AsyncSession,
    *,
    transmission: Transmission,
) -> dict[str, object]:
    device = await session.scalar(
        select(EdgeDevice)
        .where(
            EdgeDevice.organization_id == transmission.organization_id,
            EdgeDevice.site_id == transmission.site_id,
            EdgeDevice.enabled.is_(True),
        )
        .order_by(EdgeDevice.last_seen_at.desc(), EdgeDevice.created_at.desc())
        .limit(1)
    )
    if device is None:
        return dict(_DEFAULT_POLICY)
    remote_config = dict(device.remote_config or {})
    radio = remote_config.get("radio")
    radio_config = dict(radio) if isinstance(radio, dict) else {}
    ai = radio_config.get("ai_channel")
    ai_config = dict(ai) if isinstance(ai, dict) else {}
    return {**_DEFAULT_POLICY, **ai_config}


def _emergency_terms(profile: OrganizationOperationalProfile | None) -> set[str]:
    configured = set(profile.emergency_terms or []) if profile is not None else set()
    return {
        term.strip().casefold()
        for term in _DEFAULT_EMERGENCY_TERMS | configured
        if term.strip()
    }


def _detect_emergency(
    text: str,
    *,
    enabled: bool,
    terms: set[str],
) -> tuple[bool, float | None, str | None]:
    if not enabled:
        return False, None, None
    normalized = " ".join(text.casefold().split())
    matched = sorted(term for term in terms if term in normalized)
    if not matched:
        return False, None, None
    confidence = min(0.86 + (0.04 * len(matched)), 0.98)
    return True, confidence, "Emergency terms detected: " + ", ".join(matched)


def _profile_context(
    profile: OrganizationOperationalProfile | None,
    *,
    intent: SatchyIntent,
) -> dict[str, object]:
    if profile is None:
        return {"satchy_intent": intent.value}
    return {
        "profile_id": str(profile.id),
        "industry": profile.industry,
        "operation_type": profile.operation_type,
        "radio_protocol": profile.radio_protocol,
        "terminology": profile.terminology,
        "location_aliases": profile.location_aliases,
        "event_types": profile.event_types,
        "satchy_intent": intent.value,
    }


async def _radio_decision(
    session: AsyncSession,
    *,
    transmission: Transmission,
    conversation: RadioConversation,
    intent: SatchyIntent,
    policy: dict[str, object],
) -> tuple[str, dict[str, object], SatchyAction | None] | None:
    if intent not in {SatchyIntent.APPROVE_ACTION, SatchyIntent.REJECT_ACTION}:
        return None
    if not transmission.addressed_to_agent:
        return "Decision phrase was not addressed to Satchy", {}, None
    if policy.get("radio_approval_enabled") is not True:
        return "Radio action decisions are disabled by site policy", {}, None
    if transmission.speaker_callsign_id is None:
        return "Radio action decision has no attributed callsign", {}, None

    speaker = await session.scalar(
        select(Callsign).where(
            Callsign.id == transmission.speaker_callsign_id,
            Callsign.organization_id == transmission.organization_id,
        )
    )
    configured = policy.get("authorized_approver_callsigns", [])
    allowed = {
        str(item).strip().casefold()
        for item in configured
        if isinstance(item, str) and item.strip()
    }
    if speaker is None or speaker.name.casefold() not in allowed:
        return "Radio callsign is not authorized to approve Satchy actions", {}, None

    pending = await session.scalar(
        select(SatchyAction)
        .where(
            SatchyAction.organization_id == transmission.organization_id,
            SatchyAction.site_id == transmission.site_id,
            SatchyAction.conversation_id == conversation.id,
            SatchyAction.status == ActionStatus.AWAITING_APPROVAL.value,
        )
        .order_by(SatchyAction.created_at.desc())
        .limit(1)
    )
    if pending is None:
        return "No action is awaiting approval in this radio conversation", {}, None

    kwargs = {
        "organization_id": transmission.organization_id,
        "action_id": pending.id,
        "approver_role": "radio_operator",
        "approval_source": "radio",
        "approver_callsign_id": speaker.id,
        "source_transmission_id": transmission.id,
        "authorized_roles": {"radio_operator"},
    }
    if intent == SatchyIntent.REJECT_ACTION:
        action, _ = await reject_action(session, **kwargs)
        return (
            f"{speaker.name} rejected the pending Satchy action",
            {"decision": "rejected", "action_id": str(action.id)},
            action,
        )

    action, _ = await approve_action(session, **kwargs)
    queue_detail: str | None = None
    try:
        if action.action_type == ActionType.REPLY_RADIO.value:
            await queue_approved_action(
                session,
                organization_id=transmission.organization_id,
                action_id=action.id,
            )
        elif action.action_type == ActionType.ASSET_MISSION.value:
            mission_id = action.structured_payload.get("mission_id")
            if isinstance(mission_id, str):
                from uuid import UUID

                await queue_field_mission(
                    session,
                    organization_id=transmission.organization_id,
                    mission_id=UUID(mission_id),
                )
    except (InvalidConfiguration, ResourceNotFound, ValueError) as exc:
        queue_detail = str(exc)

    payload: dict[str, object] = {"decision": "approved", "action_id": str(action.id)}
    if queue_detail:
        payload["queue_detail"] = queue_detail
    return f"{speaker.name} approved the pending Satchy action", payload, action


def _mission_request(text: str) -> tuple[str, set[str], dict[str, object]]:
    lowered = text.casefold()
    if "relay" in lowered or "coverage" in lowered:
        return "relay_deploy", {"relay:deploy"}, {"requested_location": text}
    if "eyes on" in lowered or "inspect" in lowered:
        return "inspection", {"camera:capture"}, {"requested_location": text}
    return "field_deployment", {"drone:mission"}, {"requested_location": text}


async def process_transmission_control_plane(
    session: AsyncSession,
    *,
    transmission: Transmission,
    text: str,
    callsign_hint: str | None,
    operational_event: OperationalEvent | None,
) -> EvaluationOutcome:
    """Associate, understand and propose; explicit radio decisions remain human decisions."""

    existing = await session.scalar(
        select(SatchyEvaluation).where(
            SatchyEvaluation.organization_id == transmission.organization_id,
            SatchyEvaluation.source_transmission_id == transmission.id,
        )
    )
    if existing is not None:
        conversation = await session.scalar(
            select(RadioConversation).where(
                RadioConversation.id == existing.conversation_id,
                RadioConversation.organization_id == transmission.organization_id,
            )
        )
        existing_action = await session.scalar(
            select(SatchyAction).where(
                SatchyAction.organization_id == transmission.organization_id,
                SatchyAction.evaluation_id == existing.id,
            )
        )
        if conversation is None:
            raise RuntimeError("Satchy evaluation is missing its conversation")
        return EvaluationOutcome(conversation, existing, existing_action)

    policy = await _policy_for_site(session, transmission=transmission)
    profile = await get_operational_profile(
        session,
        organization_id=transmission.organization_id,
        site_id=transmission.site_id,
    )
    terms = _emergency_terms(profile)
    raw_timeout = policy.get("conversation_timeout_seconds", 300)
    timeout = max(int(raw_timeout) if isinstance(raw_timeout, (int, str)) else 300, 30)
    conversation, addressing = await associate_transmission(
        session,
        transmission=transmission,
        text=text,
        callsign_hint=callsign_hint,
        operational_event=operational_event,
        conversation_timeout_seconds=timeout,
        emergency_terms=terms,
    )
    intent = resolve_intent(text)

    decision = await _radio_decision(
        session,
        transmission=transmission,
        conversation=conversation,
        intent=intent.intent,
        policy=policy,
    )
    if decision is not None:
        interpretation, proposed_payload, decided_action = decision
        evaluation = SatchyEvaluation(
            organization_id=transmission.organization_id,
            site_id=transmission.site_id,
            conversation_id=conversation.id,
            source_transmission_id=transmission.id,
            addressed_to_satchy=addressing.addressed_to_agent,
            confidence=intent.confidence,
            interpretation=interpretation,
            proposed_action=proposed_payload,
            approval_required=False,
            emergency_candidate=False,
            operational_context=_profile_context(profile, intent=intent.intent),
        )
        session.add(evaluation)
        await session.flush()
        return EvaluationOutcome(conversation, evaluation, decided_action)

    emergency, emergency_confidence, emergency_reason = _detect_emergency(
        text,
        enabled=bool(policy.get("emergency_detection_enabled", True)),
        terms=terms,
    )
    transmission.emergency_candidate = emergency
    transmission.emergency_confidence = emergency_confidence
    transmission.emergency_reason = emergency_reason

    if (
        addressing.addressed_to_agent
        and intent.intent == SatchyIntent.REQUEST_MISSION
        and not emergency
    ):
        mission_type, capabilities, target = _mission_request(text)
        try:
            mission = await create_mission_plan(
                session,
                organization_id=transmission.organization_id,
                site_id=transmission.site_id,
                objective=text,
                mission_type=mission_type,
                required_capabilities=capabilities,
                target=target,
                requested_by_callsign_id=transmission.speaker_callsign_id,
                source_transmission_id=transmission.id,
                conversation_id=conversation.id,
            )
            mission_action = (
                await session.get(SatchyAction, mission.action_id) if mission.action_id else None
            )
            asset_name = "Authorized field asset"
            proposed = {
                "type": "asset_mission",
                "mission_id": str(mission.id),
                "asset_id": str(mission.asset_id),
            }
            evaluation = SatchyEvaluation(
                organization_id=transmission.organization_id,
                site_id=transmission.site_id,
                conversation_id=conversation.id,
                source_transmission_id=transmission.id,
                addressed_to_satchy=True,
                confidence=intent.confidence,
                interpretation=f"Field mission requested: {text}",
                proposed_action=proposed,
                approval_required=mission.approval_required,
                emergency_candidate=False,
                operational_context=_profile_context(profile, intent=intent.intent),
            )
            session.add(evaluation)
            if mission_action is not None:
                mission_action.evaluation_id = evaluation.id
            await session.flush()
            return EvaluationOutcome(conversation, evaluation, mission_action)
        except ResourceNotFound:
            pass

    action_type: ActionType | None = None
    proposed_message: str | None = None
    risk_level = "low"
    if emergency:
        action_type = ActionType.EMERGENCY_REVIEW
        risk_level = "critical"
        interpretation = emergency_reason or "Possible emergency requires human review"
    elif addressing.addressed_to_agent:
        action_type = ActionType.REPLY_RADIO
        caller = addressing.speaker_text or "Caller"
        if operational_event is not None and operational_event.event_type != "GENERAL_UPDATE":
            proposed_message = observation_logged(
                callsign=caller,
                location=operational_event.location_text,
                detail=operational_event.summary,
            )
            interpretation = "Satchy received and logged a structured field report"
        else:
            proposed_message = radio_prefix(caller) + " Go ahead."
            interpretation = f"{caller} is calling Satchy"
    else:
        interpretation = "Transmission is not explicitly addressed to Satchy"

    configured_actions = policy.get("allowed_action_types", _DEFAULT_POLICY["allowed_action_types"])
    if isinstance(configured_actions, (list, tuple, set, frozenset)):
        allowed = {str(item) for item in configured_actions}
    else:
        allowed = {item.value for item in ActionType}
    response_mode = str(policy.get("response_mode", "suggest"))
    proposed_payload: dict[str, object] = {}
    if action_type is not None and action_type.value in allowed and response_mode == "suggest":
        proposed_payload = {"type": action_type.value}
        if proposed_message is not None:
            proposed_payload["message"] = proposed_message

    evaluation = SatchyEvaluation(
        organization_id=transmission.organization_id,
        site_id=transmission.site_id,
        conversation_id=conversation.id,
        source_transmission_id=transmission.id,
        addressed_to_satchy=addressing.addressed_to_agent,
        confidence=addressing.confidence,
        interpretation=interpretation,
        proposed_action=proposed_payload,
        approval_required=True,
        emergency_candidate=emergency,
        emergency_confidence=emergency_confidence,
        emergency_reason=emergency_reason,
        operational_context=_profile_context(profile, intent=intent.intent),
    )
    session.add(evaluation)
    await session.flush()

    action: SatchyAction | None = None
    if proposed_payload and action_type is not None:
        action = SatchyAction(
            organization_id=transmission.organization_id,
            site_id=transmission.site_id,
            conversation_id=conversation.id,
            source_transmission_id=transmission.id,
            operational_event_id=operational_event.id if operational_event else None,
            evaluation_id=evaluation.id,
            action_type=action_type.value,
            risk_level=risk_level,
            reason=interpretation,
            proposed_message=proposed_message,
            structured_payload={
                "emergency_candidate": emergency,
                "emergency_auto_broadcast": False,
                "satchy_intent": intent.intent.value,
            },
            confidence=addressing.confidence if not emergency else emergency_confidence or 0.9,
            approval_required=True,
            status=ActionStatus.PROPOSED.value,
            expires_at=datetime.now(UTC) + timedelta(minutes=15),
        )
        session.add(action)
        await session.flush()
        transition_action(action, ActionStatus.AWAITING_APPROVAL)

    await session.flush()
    return EvaluationOutcome(conversation, evaluation, action)
