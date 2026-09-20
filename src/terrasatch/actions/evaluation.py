"""Structured Satchy evaluation around inbound radio context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.actions.models import ActionStatus, ActionType, SatchyAction, SatchyEvaluation
from terrasatch.actions.service import (
    approve_action,
    execute_approved_integration_action,
    queue_approved_action,
    reject_action,
)
from terrasatch.actions.state import transition_action
from terrasatch.config import Settings
from terrasatch.edge.models import EdgeDevice
from terrasatch.errors import InvalidConfiguration, ResourceNotFound
from terrasatch.organizations.models import OrganizationOperationalProfile
from terrasatch.organizations.profiles import get_operational_profile
from terrasatch.radio.conversations import associate_transmission
from terrasatch.radio.models import Callsign, OperationalEvent, RadioConversation, Transmission
from terrasatch.satchy.agent import plan_integration_action, resolve_radio_intent
from terrasatch.satchy.assets import create_mission_plan, queue_field_mission
from terrasatch.satchy.intents import resolve_intent
from terrasatch.satchy.models import FieldAsset, FieldMission
from terrasatch.satchy.radio import (
    mission_status_response,
    observation_logged,
    radio_prefix,
    summary_response,
)
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
    settings: Settings | None,
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
    integration_delivery = None
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
                await queue_field_mission(
                    session,
                    organization_id=transmission.organization_id,
                    mission_id=UUID(mission_id),
                )
        elif action.action_type in {
            ActionType.NOTIFY_TEAM.value,
            ActionType.GENERATE_REPORT.value,
        }:
            if settings is None:
                queue_detail = "Integration runtime settings are unavailable"
            else:
                _, integration_delivery, queue_detail = (
                    await execute_approved_integration_action(
                        session,
                        settings,
                        action=action,
                        approver_user_id=None,
                    )
                )
    except (InvalidConfiguration, ResourceNotFound, ValueError) as exc:
        queue_detail = str(exc)

    payload: dict[str, object] = {
        "decision": "approved",
        "action_id": str(action.id),
        "action_status": action.status,
    }
    if integration_delivery is not None:
        payload["integration_execution"] = {
            "status": integration_delivery.status,
            "delivery_id": str(integration_delivery.id),
        }
    if queue_detail:
        payload["queue_detail"] = queue_detail
    interpretation = f"{speaker.name} approved the pending Satchy action"
    if integration_delivery is not None and integration_delivery.status == "delivered":
        interpretation += " and the approved integration output was delivered"
    elif queue_detail:
        interpretation += f"; integration execution is blocked: {queue_detail}"
    return interpretation, payload, action


async def _latest_conversation_event(
    session: AsyncSession,
    *,
    transmission: Transmission,
    conversation: RadioConversation,
) -> OperationalEvent | None:
    """Return the latest prior structured event from this exact radio conversation."""

    return await session.scalar(
        select(OperationalEvent)
        .join(Transmission, Transmission.id == OperationalEvent.transmission_id)
        .where(
            OperationalEvent.organization_id == transmission.organization_id,
            OperationalEvent.site_id == transmission.site_id,
            Transmission.organization_id == transmission.organization_id,
            Transmission.site_id == transmission.site_id,
            Transmission.conversation_id == conversation.id,
            Transmission.id != transmission.id,
        )
        .order_by(OperationalEvent.created_at.desc())
        .limit(1)
    )


async def _conversation_summary(
    session: AsyncSession,
    *,
    transmission: Transmission,
    conversation: RadioConversation,
) -> tuple[str, list[str], int]:
    """Return source-backed summaries from the active radio conversation."""

    query = (
        select(OperationalEvent)
        .join(Transmission, Transmission.id == OperationalEvent.transmission_id)
        .where(
            OperationalEvent.organization_id == transmission.organization_id,
            OperationalEvent.site_id == transmission.site_id,
            Transmission.organization_id == transmission.organization_id,
            Transmission.site_id == transmission.site_id,
            Transmission.conversation_id == conversation.id,
            Transmission.id != transmission.id,
        )
        .order_by(OperationalEvent.created_at.desc())
        .limit(6)
    )
    events = list(await session.scalars(query))
    location = conversation.active_location or ""
    summaries = [event.summary for event in events if event.summary]
    return location, summaries, len(events)


async def _mission_status(
    session: AsyncSession,
    *,
    transmission: Transmission,
    conversation: RadioConversation,
) -> tuple[FieldMission, FieldAsset] | None:
    """Prefer an active mission in this conversation, then the latest site mission."""

    active_states = (
        "ready",
        "awaiting_approval",
        "queued",
        "deploying",
        "active",
        "holding",
        "returning",
    )
    speaker_team_id: UUID | None = None
    if transmission.speaker_callsign_id is not None:
        speaker = await session.scalar(
            select(Callsign).where(
                Callsign.id == transmission.speaker_callsign_id,
                Callsign.organization_id == transmission.organization_id,
            )
        )
        speaker_team_id = speaker.team_id if speaker is not None else None

    base = (
        select(FieldMission, FieldAsset)
        .join(FieldAsset, FieldAsset.id == FieldMission.asset_id)
        .where(
            FieldMission.organization_id == transmission.organization_id,
            FieldMission.site_id == transmission.site_id,
            FieldAsset.organization_id == transmission.organization_id,
            FieldAsset.enabled.is_(True),
            FieldAsset.owner_user_id.is_(None),
        )
    )
    if speaker_team_id is None:
        base = base.where(FieldAsset.team_id.is_(None))
    else:
        base = base.where(
            or_(FieldAsset.team_id.is_(None), FieldAsset.team_id == speaker_team_id)
        )
    row = (
        await session.execute(
            base.where(
                FieldMission.conversation_id == conversation.id,
                FieldMission.status.in_(active_states),
            )
            .order_by(FieldMission.created_at.desc())
            .limit(1)
        )
    ).first()
    if row is None:
        row = (
            await session.execute(
                base.where(FieldMission.status.in_(active_states))
                .order_by(FieldMission.created_at.desc())
                .limit(1)
            )
        ).first()
    if row is None:
        row = (
            await session.execute(
                base.where(FieldMission.conversation_id == conversation.id)
                .order_by(FieldMission.created_at.desc())
                .limit(1)
            )
        ).first()
    if row is None:
        return None
    mission, asset = row
    return mission, asset


def _mission_request(text: str) -> tuple[str, set[str]]:
    lowered = text.casefold()
    if "relay" in lowered or "coverage" in lowered:
        return "relay_deploy", {"relay:deploy"}
    if "eyes on" in lowered or "inspect" in lowered:
        return "inspection", {"camera:capture"}
    return "field_deployment", {"drone:mission"}


async def process_transmission_control_plane(
    session: AsyncSession,
    *,
    transmission: Transmission,
    text: str,
    callsign_hint: str | None,
    operational_event: OperationalEvent | None,
    settings: Settings | None = None,
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
    if settings is not None and addressing.addressed_to_agent:
        radio_context: dict[str, object] = {
            "conversation": {
                "active_location": conversation.active_location,
                "primary_topic": conversation.primary_topic,
                "participants": conversation.participants,
            },
            "profile": {
                "industry": profile.industry if profile else None,
                "operation_type": profile.operation_type if profile else None,
                "terminology": profile.terminology if profile else {},
                "location_aliases": profile.location_aliases if profile else {},
            },
        }
        if operational_event is not None:
            radio_context["current_event"] = {
                "type": operational_event.event_type,
                "summary": operational_event.summary,
                "location": operational_event.location_text,
                "confidence": operational_event.confidence,
            }
        intent = await resolve_radio_intent(
            settings=settings,
            text=text,
            context=radio_context,
        )

    decision = await _radio_decision(
        session,
        transmission=transmission,
        conversation=conversation,
        intent=intent.intent,
        policy=policy,
        settings=settings,
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

    integration_plan = None
    if (
        addressing.addressed_to_agent
        and intent.intent == SatchyIntent.REQUEST_ACTION
        and not emergency
    ):
        active_location, summaries, _ = await _conversation_summary(
            session,
            transmission=transmission,
            conversation=conversation,
        )
        planner_context: dict[str, object] = {
            "conversation": {
                "active_location": active_location or conversation.active_location,
                "summaries": summaries,
            }
        }
        if (
            operational_event is not None
            and operational_event.event_type != "GENERAL_UPDATE"
        ):
            planner_context["current_event"] = {
                "id": str(operational_event.id),
                "type": operational_event.event_type,
                "summary": operational_event.summary,
                "location": operational_event.location_text,
            }
        integration_plan = await plan_integration_action(
            settings=settings,
            text=text,
            context=planner_context,
        )

    mission_feedback: str | None = None
    if (
        addressing.addressed_to_agent
        and intent.intent == SatchyIntent.REQUEST_MISSION
        and not emergency
    ):
        mission_type, capabilities = _mission_request(text)
        target_location = (
            operational_event.location_text
            if operational_event is not None and operational_event.location_text
            else conversation.active_location
        )
        if not target_location:
            mission_feedback = "I don't have a confident mission location. Say location again."
        else:
            speaker_team_id = None
            if transmission.speaker_callsign_id is not None:
                speaker_callsign = await session.scalar(
                    select(Callsign).where(
                        Callsign.id == transmission.speaker_callsign_id,
                        Callsign.organization_id == transmission.organization_id,
                    )
                )
                speaker_team_id = speaker_callsign.team_id if speaker_callsign else None
            target = {
                "location_text": target_location,
                "provenance": (
                    "operational_event"
                    if operational_event is not None and operational_event.location_text
                    else "active_conversation"
                ),
            }
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
                    team_id=speaker_team_id,
                    source_transmission_id=transmission.id,
                    conversation_id=conversation.id,
                )
                mission_action = (
                    await session.get(SatchyAction, mission.action_id)
                    if mission.action_id
                    else None
                )
                proposed = {
                    "type": "asset_mission",
                    "mission_id": str(mission.id),
                    "asset_id": str(mission.asset_id),
                    "target": target,
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
                await session.flush()
                if mission_action is not None:
                    mission_action.evaluation_id = evaluation.id
                elif not mission.approval_required:
                    try:
                        await queue_field_mission(
                            session,
                            organization_id=transmission.organization_id,
                            mission_id=mission.id,
                        )
                    except InvalidConfiguration as exc:
                        evaluation.operational_context = {
                            **evaluation.operational_context,
                            "mission_queue_detail": str(exc),
                        }
                await session.flush()
                return EvaluationOutcome(conversation, evaluation, mission_action)
            except ResourceNotFound:
                mission_feedback = (
                    "No authorized available field asset can satisfy that mission."
                )

    action_type: ActionType | None = None
    proposed_message: str | None = None
    risk_level = "low"
    action_specific_payload: dict[str, object] = {}
    if emergency:
        action_type = ActionType.EMERGENCY_REVIEW
        risk_level = "critical"
        interpretation = emergency_reason or "Possible emergency requires human review"
    elif addressing.addressed_to_agent:
        caller = addressing.speaker_text or "Caller"
        if intent.intent == SatchyIntent.REQUEST_ACTION and integration_plan is not None:
            if integration_plan.missing_context:
                action_type = ActionType.ASK_CLARIFICATION
                missing = ", ".join(integration_plan.missing_context)
                proposed_message = (
                    f"{radio_prefix(caller)} I need {missing} before I can propose that action."
                )
                interpretation = integration_plan.summary
            elif (
                integration_plan.action_type == "notify_team"
                and integration_plan.notification_text
            ):
                action_type = ActionType.NOTIFY_TEAM
                proposed_message = integration_plan.notification_text
                interpretation = integration_plan.summary
                action_specific_payload = {
                    "capability": "notification.send",
                    "text": integration_plan.notification_text,
                    "workflow_key": "satchy.action.notify_team",
                    "planner_confidence": integration_plan.confidence,
                }
            elif (
                integration_plan.action_type == "generate_report"
                and integration_plan.document_content
                and integration_plan.document_name
                and integration_plan.mime_type
            ):
                action_type = ActionType.GENERATE_REPORT
                proposed_message = integration_plan.document_content
                interpretation = integration_plan.summary
                action_specific_payload = {
                    "capability": "document.create",
                    "name": integration_plan.document_name,
                    "content": integration_plan.document_content,
                    "mime_type": integration_plan.mime_type,
                    "workflow_key": "satchy.action.generate_report",
                    "planner_confidence": integration_plan.confidence,
                }
            else:
                action_type = ActionType.ASK_CLARIFICATION
                proposed_message = (
                    f"{radio_prefix(caller)} Tell me what you want sent or reported."
                )
                interpretation = "Integration action request needs clarification"
        elif intent.intent == SatchyIntent.REQUEST_MISSION and mission_feedback:
            action_type = (
                ActionType.ASK_CLARIFICATION
                if "location" in mission_feedback.casefold()
                else ActionType.REPLY_RADIO
            )
            proposed_message = f"{radio_prefix(caller)} {mission_feedback}"
            interpretation = mission_feedback
        elif intent.intent == SatchyIntent.LOG_OBSERVATION:
            if operational_event is not None and operational_event.event_type != "GENERAL_UPDATE":
                action_type = ActionType.REPLY_RADIO
                proposed_message = observation_logged(
                    callsign=caller,
                    location=operational_event.location_text,
                    detail=operational_event.summary,
                )
                interpretation = "Satchy logged the current structured field report"
            else:
                previous = await _latest_conversation_event(
                    session,
                    transmission=transmission,
                    conversation=conversation,
                )
                action_type = ActionType.REPLY_RADIO
                if previous is None:
                    proposed_message = (
                        f"{radio_prefix(caller)} I don't have a previous structured report to log."
                    )
                    interpretation = "No prior structured report exists in this conversation"
                else:
                    proposed_message = (
                        f"{radio_prefix(caller)} Last report is already logged. "
                        f"{previous.summary.strip().rstrip('.')}."
                    )
                    interpretation = (
                        f"Referenced prior event {previous.id}; no duplicate observation created"
                    )
        elif intent.intent == SatchyIntent.REPEAT:
            previous = await _latest_conversation_event(
                session,
                transmission=transmission,
                conversation=conversation,
            )
            action_type = ActionType.REPLY_RADIO
            if previous is None:
                proposed_message = (
                    f"{radio_prefix(caller)} No previous structured report to repeat."
                )
                interpretation = "No prior structured report exists in this conversation"
            else:
                location = (
                    f" {previous.location_text.strip().rstrip('.')}."
                    if previous.location_text
                    else ""
                )
                proposed_message = (
                    f"{radio_prefix(caller)} Last report.{location} "
                    f"{previous.summary.strip().rstrip('.')}."
                )
                interpretation = f"Repeated prior source-backed event {previous.id}"
        elif intent.intent == SatchyIntent.SUMMARIZE:
            location, summaries, count = await _conversation_summary(
                session,
                transmission=transmission,
                conversation=conversation,
            )
            action_type = ActionType.REPLY_RADIO
            proposed_message = summary_response(
                caller,
                count=count,
                summaries=summaries,
                location=location or None,
            )
            interpretation = (
                f"Satchy summarized {count} source-backed report(s)"
                + (f" for {location}" if location else "")
            )
        elif intent.intent == SatchyIntent.MISSION_STATUS:
            current = await _mission_status(
                session,
                transmission=transmission,
                conversation=conversation,
            )
            action_type = ActionType.REPLY_RADIO
            if current is None:
                proposed_message = f"{radio_prefix(caller)} No field mission is currently recorded."
                interpretation = "No field mission is available for this context"
            else:
                mission, asset = current
                proposed_message = mission_status_response(
                    caller,
                    asset_name=asset.name,
                    status=mission.status,
                    objective=mission.objective,
                )
                interpretation = (
                    f"Reported stored mission status {mission.status} for {asset.name}"
                )
        elif operational_event is not None and operational_event.event_type != "GENERAL_UPDATE":
            action_type = ActionType.REPLY_RADIO
            proposed_message = observation_logged(
                callsign=caller,
                location=operational_event.location_text,
                detail=operational_event.summary,
            )
            interpretation = "Satchy received and logged a structured field report"
        else:
            action_type = ActionType.REPLY_RADIO
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
        if action_type in {ActionType.NOTIFY_TEAM, ActionType.GENERATE_REPORT}:
            proposed_payload["approval_required"] = True
            proposed_payload["capability"] = action_specific_payload.get("capability")

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
                **action_specific_payload,
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