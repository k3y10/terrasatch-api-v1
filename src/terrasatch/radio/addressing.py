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
    pattern: str = "unresolved"
    message_text: str = ""


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
    if not matches:
        return None
    longest = max(length for length, _ in matches)
    winners = {candidate.id: candidate for length, candidate in matches if length == longest}
    return next(iter(winners.values())) if len(winners) == 1 else None


def parse_radio_addressing(
    text: str,
    *,
    callsigns: list[CallsignCandidate],
    agent_names: set[str] | None = None,
    callsign_hint: str | None = None,
    emergency_terms: set[str] | None = None,
) -> AddressingResolution:
    """Resolve only configured labels at explicit, deterministic radio boundaries."""
    agents = {_normalized(name) for name in (agent_names or {"Satchy"}) if _clean(name)}
    labels = {_clean(label) for c in callsigns for label in _labels(c) if _clean(label)}
    labels.update(_clean(name) for name in (agent_names or {"Satchy"}) if _clean(name))
    alternatives = "|".join(
        re.escape(label) for label in sorted(labels, key=lambda x: (-len(x), x))
    )
    normalized = " ".join(text.split()).strip()
    speaker = recipient = None
    speaker_text = recipient_text = None
    addressed = False
    pattern_name = "unresolved"
    message = normalized

    if alternatives:
        label = f"(?:{alternatives})"
        boundary = r"(?=$|[,.;:!?])"
        patterns = [
            ("to", rf"(?P<speaker>{label}) to (?P<recipient>{label}){boundary}"),
            ("calling", rf"(?P<speaker>{label}) calling (?P<recipient>{label}){boundary}"),
            ("this_is", rf"(?P<recipient>{label}),? this is (?P<speaker>{label}){boundary}"),
            ("from", rf"(?P<recipient>{label}) from (?P<speaker>{label}){boundary}"),
            ("for", rf"(?P<speaker>{label}) for (?P<recipient>{label}){boundary}"),
            ("recipient_first", rf"(?P<recipient>{label})[,;] *(?P<speaker>{label}){boundary}"),
            ("recipient_only", rf"(?P<recipient>{label}){boundary}"),
        ]
        for name, pattern in patterns:
            match = re.match(pattern, normalized, re.I)
            if match is None:
                continue
            raw_recipient = match.group("recipient")
            recipient = _match(raw_recipient, callsigns, allow_prefix=False)
            raw_speaker = match.groupdict().get("speaker")
            speaker = _match(raw_speaker, callsigns, allow_prefix=False) if raw_speaker else None
            # Colliding aliases must not silently select a participant.
            if recipient is None and _normalized(raw_recipient) not in agents:
                break
            if raw_speaker and speaker is None and _normalized(raw_speaker) not in agents:
                break
            recipient_text = recipient.name if recipient else _clean(raw_recipient)
            speaker_text = speaker.name if speaker else raw_speaker
            addressed = _normalized(recipient_text) in agents or (
                recipient is not None and any(_normalized(x) in agents for x in _labels(recipient))
            )
            pattern_name = name
            message = normalized[match.end() :].lstrip(" ,.;:!?")
            break

    if speaker_text is None and callsign_hint:
        speaker = _match(callsign_hint, callsigns, allow_prefix=False)
        speaker_text = speaker.name if speaker else _clean(callsign_hint)[:255] or None
        if pattern_name == "unresolved":
            pattern_name = "callsign_hint"
    confidence = (
        0.94
        if addressed and recipient and speaker
        else 0.88
        if addressed and speaker_text
        else 0.82
        if addressed
        else 0.80
        if recipient and speaker
        else 0.55
        if recipient_text or speaker_text
        else 0.20
    )
    return AddressingResolution(
        speaker_callsign_id=speaker.id if speaker else None,
        recipient_callsign_id=recipient.id if recipient else None,
        speaker_text=speaker_text,
        recipient_text=recipient_text,
        addressed_to_agent=addressed,
        confidence=confidence,
        pattern=pattern_name,
        message_text=message,
    )
