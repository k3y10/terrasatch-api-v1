"""Conservative radio-native intent resolution for Satchy."""

from __future__ import annotations

import re

from .schemas import IntentResolution, SatchyIntent

_CONTEXT_REFERENCE = re.compile(
    r"\b(?:that|there|it|last one|last report|this area|this one|send it|log that)\b",
    re.I,
)
_EXPLICIT_APPROVE = re.compile(
    r"\b(?:approve|confirm)(?:\s+(?:it|send|action|mission|deployment))?\b",
    re.I,
)
_EXPLICIT_REJECT = re.compile(
    r"\b(?:reject|deny)(?:\s+(?:it|action|mission))?\b"
    r"|\b(?:do not|don't|cannot|can't)\s+approve\b",
    re.I,
)
_EXPLICIT_CANCEL = re.compile(r"\b(?:cancel|scratch|stand down)(?:\s+(?:it|that))?\b", re.I)
_ABORT_MISSION = re.compile(r"\b(?:abort mission|abort deployment|bring it back|return to base)\b", re.I)
_MISSION_STATUS = re.compile(
    r"\b(?:mission status|status of|what(?:'s| is)\s+(?:the\s+)?(?:drone|robot|relay))\b",
    re.I,
)
_REQUEST_MISSION = re.compile(
    r"\b(?:deploy|launch|send the drone|send drone|get eyes on|inspect|establish coverage|"
    r"position the relay|deploy the relay)\b",
    re.I,
)
_LOG_OBSERVATION = re.compile(
    r"\b(?:log that|log this|log observation|record that|record this|"
    r"field observation|add (?:that|this) (?:to )?(?:the )?log)\b",
    re.I,
)
_SUMMARIZE = re.compile(r"\b(?:summarize|summary|handoff|recap)\b", re.I)
_REPEAT = re.compile(r"\b(?:repeat|say again|what did .* say|remind me)\b", re.I)
_CORRECT = re.compile(r"\b(?:correction|correct that|not .{1,80},?\s*(?:it was|make that))\b", re.I)
_CREATE_TASK = re.compile(r"\b(?:create|add|make)\s+(?:a\s+)?task\b", re.I)
_QUESTION = re.compile(
    r"^(?:satchy[, ]+)?(?:what|where|when|who|why|how|is|are|do|did|can|could|which)\b",
    re.I,
)


def resolve_intent(text: str) -> IntentResolution:
    """Resolve obvious operational intent without treating conversational text as authorization."""

    normalized = " ".join(text.split()).strip()
    references = bool(_CONTEXT_REFERENCE.search(normalized))
    checks: tuple[tuple[re.Pattern[str], SatchyIntent, float], ...] = (
        (_ABORT_MISSION, SatchyIntent.ABORT_MISSION, 0.98),
        (_MISSION_STATUS, SatchyIntent.MISSION_STATUS, 0.95),
        (_EXPLICIT_REJECT, SatchyIntent.REJECT_ACTION, 0.97),
        (_EXPLICIT_APPROVE, SatchyIntent.APPROVE_ACTION, 0.96),
        (_EXPLICIT_CANCEL, SatchyIntent.CANCEL_ACTION, 0.94),
        (_REQUEST_MISSION, SatchyIntent.REQUEST_MISSION, 0.92),
        (_LOG_OBSERVATION, SatchyIntent.LOG_OBSERVATION, 0.94),
        (_SUMMARIZE, SatchyIntent.SUMMARIZE, 0.93),
        (_REPEAT, SatchyIntent.REPEAT, 0.91),
        (_CORRECT, SatchyIntent.CORRECT_RECORD, 0.9),
        (_CREATE_TASK, SatchyIntent.CREATE_TASK, 0.92),
        (_QUESTION, SatchyIntent.QUESTION, 0.85),
    )
    for pattern, intent, confidence in checks:
        if pattern.search(normalized):
            return IntentResolution(
                intent=intent,
                confidence=confidence,
                explicit=True,
                references_context=references,
            )
    return IntentResolution(
        intent=SatchyIntent.INFORMATION,
        confidence=0.7 if normalized else 0.0,
        explicit=False,
        references_context=references,
    )