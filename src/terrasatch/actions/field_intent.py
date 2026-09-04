"""Explicit field workflow intent and bounded operational-memory proposals.

No extraction, persistence of duplicate observations, or external execution occurs here.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.actions.models import ActionType
from terrasatch.radio.addressing import AddressingResolution
from terrasatch.radio.models import OperationalEvent, Transmission


def classify_field_intent(message: str) -> ActionType | None:
    text = " ".join(message.casefold().split()).strip(" ,.;:!?")
    text = re.sub(r"^please\s+", "", text)
    rules = [
        (
            r"^(?:prepare|generate|draft) (?:my |the |a )?(?:field |shift |end-of-shift )?"
            r"(?:report|handoff)\b|^summarize my observations\b",
            ActionType.GENERATE_REPORT,
        ),
        (
            r"^(?:add (?:that|this|it) to (?:the )?(?:current )?(?:incident|event)|"
            r"update (?:the |current )?event)\b",
            ActionType.UPDATE_EVENT,
        ),
        (r"^notify\s+\S+", ActionType.NOTIFY_TEAM),
        (
            r"^(?:(?:log|record) (?:this|that|an?|the)(?:\s|$)|note (?:that|for)\b)",
            ActionType.CREATE_OBSERVATION,
        ),
    ]
    for pattern, action in rules:
        if re.search(pattern, text):
            return action
    if re.match(r"^(?:field )?(?:observation|snowpit|note for|weather)\b", text):
        return None
    if re.match(r"^(?:winds?|light wind|no cracking|no avalanche)\b", text):
        return None
    if not text or re.match(r"^(?:how copy|radio check|status update|go ahead)\b", text):
        return ActionType.REPLY_RADIO
    if "?" in message:
        return ActionType.REPLY_RADIO
    # An unknown command is reviewed rather than being executed as a guessed workflow.
    if re.match(r"^(?:log|record|add|update|notify|prepare|generate|draft|summarize)\b", text):
        return ActionType.ASK_CLARIFICATION
    return None


def location_candidates(message: str, aliases: dict[str, object]) -> list[str]:
    """Support canonical-name -> aliases and alias -> canonical-name profile entries."""
    match = re.search(r"\b(?:at|near)\s+([^,.;!?]+)", message, re.I)
    if not match:
        return []
    query = " ".join(match.group(1).casefold().split())
    exact: set[str] = set()
    partial: set[str] = set()
    for key, value in aliases.items():
        if isinstance(value, str):
            canonical, labels = value, [key, value]
        elif isinstance(value, list):
            canonical, labels = key, [key, *(x for x in value if isinstance(x, str))]
        else:
            continue
        for label in labels:
            normalized = " ".join(label.casefold().split())
            if normalized == query:
                exact.add(canonical)
            elif normalized.startswith(query + " "):
                partial.add(canonical)
    return sorted(exact or partial)


async def workflow_context(
    session: AsyncSession,
    *,
    transmission: Transmission,
    addressing: AddressingResolution,
    action_type: ActionType,
    operational_event: OperationalEvent | None,
) -> dict[str, object]:
    """Stage explicit source links; never use an unscoped latest-event lookup."""
    context: dict[str, object] = {
        "organization_id": str(transmission.organization_id),
        "site_id": str(transmission.site_id),
        "source_transmission_id": str(transmission.id),
        "conversation_id": str(transmission.conversation_id),
        "channel_id": str(transmission.channel_id) if transmission.channel_id else None,
        "speaker_callsign_id": str(addressing.speaker_callsign_id)
        if addressing.speaker_callsign_id
        else None,
        "speaker": addressing.speaker_text,
        "source_operational_event_id": str(operational_event.id) if operational_event else None,
        "request_text": addressing.message_text,
        "execution": "proposal_only",
    }
    if action_type == ActionType.CREATE_OBSERVATION:
        substantive = operational_event is not None and operational_event.event_type in {
            "OBSERVATION",
            "WEATHER",
            "HAZARD",
            "MEDICAL",
            "AVALANCHE",
            "FIRE",
            "ROAD_STATUS",
            "LOCATION_UPDATE",
            "SHIFT_NOTE",
        }
        context["mode"] = "associate_or_enrich" if substantive else "stage_reference"
        context["requires_source_selection"] = not substantive
        context["insert_duplicate_observation"] = False
    if action_type == ActionType.UPDATE_EVENT:
        # A conversation can contain many events. Offer candidates, never equate its
        # first event (often a radio check) with an incident.
        events = list(
            await session.scalars(
                select(OperationalEvent)
                .join(Transmission, OperationalEvent.transmission_id == Transmission.id)
                .where(
                    OperationalEvent.organization_id == transmission.organization_id,
                    OperationalEvent.site_id == transmission.site_id,
                    Transmission.organization_id == transmission.organization_id,
                    Transmission.site_id == transmission.site_id,
                    Transmission.conversation_id == transmission.conversation_id,
                    Transmission.id != transmission.id,
                    Transmission.received_at <= transmission.received_at,
                    OperationalEvent.event_type.in_(["INCIDENT", "MEDICAL", "AVALANCHE", "FIRE"]),
                )
                .order_by(Transmission.received_at.desc())
                .limit(2)
            )
        )
        context["target_event_id"] = str(events[0].id) if len(events) == 1 else None
        context["requires_target_selection"] = len(events) != 1
        context["candidate_event_ids"] = [str(event.id) for event in events]
    if action_type == ActionType.NOTIFY_TEAM:
        context["recipient_text"] = re.split(
            r"\s+about\s+",
            re.sub(r"^(?:please\s+)?notify\s+", "", addressing.message_text, flags=re.I),
            maxsplit=1,
            flags=re.I,
        )[0].strip(" .")
        context["requires_recipient_confirmation"] = True
    if action_type == ActionType.GENERATE_REPORT:
        now = transmission.received_at or datetime.now(UTC)
        now = now.replace(tzinfo=UTC) if now.tzinfo is None else now.astimezone(UTC)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        context["scope"] = {
            "timezone": "UTC",
            "start_at": start.isoformat(),
            "end_at": now.isoformat(),
            "time_basis": "received_at",
            "window": "utc_calendar_day_to_request",
            "requires_time_window_confirmation": True,
        }
        context["report_kind"] = (
            "handoff" if "handoff" in addressing.message_text.casefold() else "field_report"
        )
        if addressing.speaker_callsign_id is None:
            context["requires_operator_identification"] = True
            return context
        transmissions = list(
            await session.scalars(
                select(Transmission)
                .where(
                    Transmission.organization_id == transmission.organization_id,
                    Transmission.site_id == transmission.site_id,
                    Transmission.speaker_callsign_id == addressing.speaker_callsign_id,
                    Transmission.received_at >= start,
                    Transmission.received_at <= now,
                    Transmission.id != transmission.id,
                )
                .order_by(Transmission.received_at, Transmission.id)
                .limit(501)
            )
        )
        context["truncated"] = len(transmissions) > 500
        transmissions = transmissions[:500]
        ids = [item.id for item in transmissions]
        context["transmission_ids"] = [str(item) for item in ids]
        context["conversation_ids"] = sorted(
            {
                str(item.conversation_id)
                for item in transmissions
                if item.conversation_id is not None
            }
        )
        events = (
            list(
                await session.scalars(
                    select(OperationalEvent.id)
                    .where(
                        OperationalEvent.organization_id == transmission.organization_id,
                        OperationalEvent.site_id == transmission.site_id,
                        OperationalEvent.transmission_id.in_(ids),
                    )
                    .order_by(OperationalEvent.id)
                )
            )
            if ids
            else []
        )
        context["operational_event_ids"] = [str(item) for item in events]
    return context
