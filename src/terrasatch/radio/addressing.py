"""Deterministic radio-order callsign and recipient interpretation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID

_TRAILING_PUNCTUATION = " .,:;!?-\u2013\u2014"


@dataclass(frozen=True, slots=True)
class CallsignCandidate:
    id: UUID
    name: str
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AddressingResolution:
    speaker_callsign_id: UUID | None
    recipient_callsign_id: UUID | None
    speaker_text: str | None
    recipient_text: str | None
    addressed_to_agent: bool
    confidence: float


def _clean(value: str) -> str:
    return " ".join(value.strip(_TRAILING_PUNCTUATION).split())


def _normalized(value: str) -> str:
    return _clean(value).casefold()


def _labels(candidate: CallsignCandidate) -> tuple[str, ...]:
    return tuple(
        sorted(
            {candidate.name, *candidate.aliases},
            key=lambda item: len(item),
            reverse=True,
        )
    )


def _match(
    fragment: str,
    candidates: list[CallsignCandidate],
    *,
    allow_prefix: bool,
) -> CallsignCandidate | None:
    normalized_fragment = _normalized(fragment)
    matches: list[tuple[int, CallsignCandidate]] = []
    for candidate in candidates:
        for label in _labels(candidate):
            normalized_label = _normalized(label)
            exact = normalized_fragment == normalized_label
            prefixed = allow_prefix and normalized_fragment.startswith(f"{normalized_label} ")
            if exact or prefixed:
                matches.append((len(normalized_label), candidate))
    return max(matches, key=lambda item: item[0])[1] if matches else None


def _agent_recipient(fragment: str, agent_names: set[str]) -> str | None:
    normalized_fragment = _normalized(fragment)
    for name in sorted(agent_names, key=len, reverse=True):
        normalized_name = _normalized(name)
        if normalized_fragment == normalized_name or normalized_fragment.startswith(
            f"{normalized_name} "
        ):
            return _clean(name)
    return None


def parse_radio_addressing(
    text: str,
    *,
    callsigns: list[CallsignCandidate],
    agent_names: set[str] | None = None,
    callsign_hint: str | None = None,
    emergency_terms: set[str] | None = None,
) -> AddressingResolution:
    """Parse recipient-first radio order without delegating boundaries to an LLM."""

    configured_agents = {name for name in (agent_names or {"Satchy"}) if name.strip()}
    fragments = [_clean(item) for item in re.split(r"[,;\n]+", text, maxsplit=2)]
    first = fragments[0] if fragments else ""
    second = _clean(fragments[1].split(".", maxsplit=1)[0]) if len(fragments) > 1 else ""

    recipient = _match(first, callsigns, allow_prefix=True)
    speaker = _match(second, callsigns, allow_prefix=False) if second else None
    recipient_agent_name = _agent_recipient(first, configured_agents)
    addressed_to_agent = recipient_agent_name is not None

    recipient_text: str | None = None
    if recipient is not None:
        recipient_text = recipient.name
    elif recipient_agent_name is not None:
        recipient_text = recipient_agent_name
    elif first:
        recipient_text = first[:255]

    speaker_text: str | None = speaker.name if speaker is not None else None
    if speaker_text is None and callsign_hint:
        speaker_text = _clean(callsign_hint)[:255] or None
    if speaker_text is None and second:
        normalized_text = text.casefold()
        is_emergency = any(
            term.casefold() in normalized_text for term in (emergency_terms or set()) if term
        )
        if not is_emergency and len(second) <= 64:
            speaker_text = second[:255]

    if addressed_to_agent and recipient is not None and speaker is not None:
        confidence = 0.94
    elif addressed_to_agent and speaker_text:
        confidence = 0.88
    elif addressed_to_agent:
        confidence = 0.82
    elif recipient is not None and speaker is not None:
        confidence = 0.80
    elif recipient_text:
        confidence = 0.55
    else:
        confidence = 0.20

    return AddressingResolution(
        speaker_callsign_id=speaker.id if speaker is not None else None,
        recipient_callsign_id=recipient.id if recipient is not None else None,
        speaker_text=speaker_text,
        recipient_text=recipient_text,
        addressed_to_agent=addressed_to_agent,
        confidence=confidence,
    )
