"""Provider-neutral TerraEngine extraction for TerraSatch operational intelligence."""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, Field


class EventType(StrEnum):
    RADIO_TRANSMISSION = "RADIO_TRANSMISSION"
    OBSERVATION = "OBSERVATION"
    HAZARD = "HAZARD"
    INCIDENT = "INCIDENT"
    TASK = "TASK"
    REQUEST = "REQUEST"
    RESPONSE = "RESPONSE"
    LOCATION_UPDATE = "LOCATION_UPDATE"
    RESOURCE_REQUEST = "RESOURCE_REQUEST"
    MEDICAL = "MEDICAL"
    WEATHER = "WEATHER"
    AVALANCHE = "AVALANCHE"
    FIRE = "FIRE"
    ROAD_STATUS = "ROAD_STATUS"
    EQUIPMENT = "EQUIPMENT"
    PERSONNEL = "PERSONNEL"
    SHIFT_NOTE = "SHIFT_NOTE"
    GENERAL_UPDATE = "GENERAL_UPDATE"


class ExtractedEvent(BaseModel):
    """Validated structured interpretation emitted by an intelligence provider."""

    event_type: EventType
    summary: str = Field(min_length=1, max_length=1000)
    callsign: str | None = None
    location_text: str | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    elevation_ft: int | None = None
    aspect: str | None = None
    severity: str | None = None
    confidence: float = Field(ge=0, le=1)
    data: dict[str, object] = Field(default_factory=dict)


class IntelligenceProvider(Protocol):
    async def extract_events(
        self,
        *,
        text: str,
        callsign_hint: str | None = None,
    ) -> list[ExtractedEvent]: ...


_ASPECTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b(?:north|northern|north-facing)\b", re.I), "N"),
    (re.compile(r"\b(?:northeast|north-east|northeastern|northeast-facing)\b", re.I), "NE"),
    (re.compile(r"\b(?:east|eastern|east-facing)\b", re.I), "E"),
    (re.compile(r"\b(?:southeast|south-east|southeastern|southeast-facing)\b", re.I), "SE"),
    (re.compile(r"\b(?:south|southern|south-facing)\b", re.I), "S"),
    (re.compile(r"\b(?:southwest|south-west|southwestern|southwest-facing)\b", re.I), "SW"),
    (re.compile(r"\b(?:west|western|west-facing)\b", re.I), "W"),
    (re.compile(r"\b(?:northwest|north-west|northwestern|northwest-facing)\b", re.I), "NW"),
)

_CALLSIGN_RE = re.compile(
    r"\b((?:patrol|dispatch|base|unit|crew|team|ops|operations)\s+[A-Za-z0-9-]+)\b",
    re.I,
)
_LOCATION_RE = re.compile(
    r"\b(?:near|at|on|below|above|toward|towards)\s+(?:the\s+)?([A-Za-z][A-Za-z0-9' -]{2,80})",
    re.I,
)
_FIELD_OBSERVATION_LOCATION_RE = re.compile(
    r"\bfield observation\b\s*[.:,-]?\s*(?:(?:at|near|on)\s+)?(?:the\s+)?"
    r"([A-Za-z][A-Za-z0-9' -]{2,80}?)"
    r"(?=\s*(?:[,.;]|(?:north(?:east|west)?|south(?:east|west)?|east|west)"
    r"(?:[- ]facing)?\s+(?:aspect|terrain)\b|no\s+(?:avalanche|avalanches|slide|slides)\b|"
    r"sunny\b|clear\b|everything\b|$))",
    re.I,
)
_NUMERIC_ELEVATION_RE = re.compile(
    r"\b(?:around|roughly|about|approximately)?\s*(?:(\d{1,2},\d{3}|\d{4,5})\s*(?:feet|ft)?|(\d{1,3})\s*(?:feet|ft))\b",
    re.I,
)
_NEGATED_AVALANCHE_RE = re.compile(
    r"\b(?:no|without)\s+(?:(?:signs?|evidence)\s+of\s+)?(?:avalanche(?:s| activity)?|slides?)\b"
    r"(?:\s+(?:observed|seen|reported|noted))?"
    r"|\b(?:avalanche(?:s| activity)?|slides?)\s+(?:was|were)?\s*not\s+"
    r"(?:observed|seen|reported|noted)\b",
    re.I,
)
_NEGATED_CRACK_RE = re.compile(
    r"\b(?:no|without)\s+(?:shooting\s+)?cracks?\b(?:\s+(?:observed|seen|reported|noted))?"
    r"|\bshooting\s+cracks?\s+(?:were)?\s*not\s+(?:observed|seen|reported|noted)\b",
    re.I,
)
_NEGATED_COLLAPSE_RE = re.compile(
    r"\b(?:no|without)\s+(?:collaps(?:e|es|ing)|whumpf(?:ing)?|whumph(?:ing)?)\b"
    r"(?:\s+(?:observed|heard|reported|noted))?",
    re.I,
)


class DeterministicIntelligenceProvider:
    """Conservative zero-cost rules provider and offline fallback."""

    name = "deterministic"

    async def extract_events(
        self,
        *,
        text: str,
        callsign_hint: str | None = None,
    ) -> list[ExtractedEvent]:
        normalized = " ".join(text.split()).strip()
        if not normalized:
            return []

        lowered = normalized.casefold()
        callsign = callsign_hint.strip() if callsign_hint and callsign_hint.strip() else None
        if callsign is None:
            match = _CALLSIGN_RE.search(normalized)
            if match:
                callsign = " ".join(part.capitalize() for part in match.group(1).split())

        aspect = self._extract_aspect(normalized)
        elevation_ft = self._extract_elevation(normalized)
        location_text = self._extract_location(normalized)
        event_type, severity, summary = self._classify(lowered, normalized)

        data: dict[str, object] = {"intelligence_provider": self.name}
        keywords = self._keywords(lowered)
        if keywords:
            data["keywords"] = keywords

        negative_findings = self._negative_findings(lowered)
        if negative_findings:
            data["negative_findings"] = negative_findings
        if "avalanche" in negative_findings:
            data["observation"] = "No avalanche observed"
            data["avalanche_problem"] = "None observed"

        weather_conditions = [
            condition
            for condition in ("sunny", "clear", "snowing", "rain")
            if re.search(rf"\b{re.escape(condition)}\b", lowered)
        ]
        if weather_conditions:
            data["weather_conditions"] = weather_conditions

        if re.search(r"\b(?:everything is|all)\s+green\b", lowered):
            data["field_status"] = "green"

        return [
            ExtractedEvent(
                event_type=event_type,
                summary=summary,
                callsign=callsign,
                location_text=location_text,
                elevation_ft=elevation_ft,
                aspect=aspect,
                severity=severity,
                confidence=self._confidence(
                    event_type=event_type,
                    callsign=callsign,
                    aspect=aspect,
                    elevation_ft=elevation_ft,
                    keywords=keywords,
                ),
                data=data,
            )
        ]

    @staticmethod
    def _extract_aspect(text: str) -> str | None:
        ordered = sorted(_ASPECTS, key=lambda item: len(item[0].pattern), reverse=True)
        for pattern, aspect in ordered:
            if pattern.search(text):
                return aspect
        return None

    @staticmethod
    def _extract_elevation(text: str) -> int | None:
        numeric = _NUMERIC_ELEVATION_RE.search(text)
        if numeric:
            value = numeric.group(1) or numeric.group(2)
            assert value is not None
            return int(value.replace(",", ""))

        word_patterns = {
            r"\bninety[- ]eight hundred\b": 9800,
            r"\bninety[- ]five hundred\b": 9500,
            r"\bten thousand\b": 10000,
            r"\beleven thousand\b": 11000,
        }
        for pattern, value in word_patterns.items():
            if re.search(pattern, text, re.I):
                return value
        return None

    @staticmethod
    def _extract_location(text: str) -> str | None:
        field_match = _FIELD_OBSERVATION_LOCATION_RE.search(text)
        if field_match:
            candidate = field_match.group(1).strip(" ,.-")
            if candidate:
                return candidate

        match = _LOCATION_RE.search(text)
        if not match:
            return None
        candidate = match.group(1)
        candidate = re.split(
            r"\b(?:around|roughly|about|approximately|with|and|but|we're|we are|at)\b",
            candidate,
            maxsplit=1,
            flags=re.I,
        )[0]
        candidate = candidate.strip(" ,.-")
        return candidate or None

    @staticmethod
    def _positive_text(lowered: str) -> str:
        text = lowered
        for pattern in (_NEGATED_AVALANCHE_RE, _NEGATED_CRACK_RE, _NEGATED_COLLAPSE_RE):
            text = pattern.sub(" ", text)
        return " ".join(text.split())

    @staticmethod
    def _negative_findings(lowered: str) -> list[str]:
        findings: list[str] = []
        if _NEGATED_AVALANCHE_RE.search(lowered):
            findings.append("avalanche")
        if _NEGATED_CRACK_RE.search(lowered):
            findings.append("shooting_cracks")
        if _NEGATED_COLLAPSE_RE.search(lowered):
            findings.append("collapse")
        return findings

    @classmethod
    def _classify(cls, lowered: str, original: str) -> tuple[EventType, str | None, str]:
        positive_text = cls._positive_text(lowered)
        negative_findings = cls._negative_findings(lowered)

        if "mayday" in positive_text or "missing person" in positive_text:
            return EventType.INCIDENT, "high", "High-priority incident reported."
        if any(term in positive_text for term in ("burial", "buried", "avalanche", "slide")):
            severity = "high" if "burial" in positive_text else "moderate"
            return EventType.AVALANCHE, severity, "Avalanche-related field report received."
        if "shooting cracks" in positive_text or "shooting crack" in positive_text:
            return EventType.OBSERVATION, "moderate", "Shooting cracks reported."
        if "collapse" in positive_text or "whumpf" in positive_text or "whumph" in positive_text:
            return EventType.HAZARD, "moderate", "Snowpack instability reported."
        if "avalanche" in negative_findings:
            return EventType.OBSERVATION, None, "No avalanche activity observed."
        if "shooting_cracks" in negative_findings:
            return EventType.OBSERVATION, None, "No shooting cracks observed."
        if "collapse" in negative_findings:
            return EventType.OBSERVATION, None, "No snowpack collapse observed."
        if any(term in positive_text for term in ("injury", "injured", "medical")):
            return EventType.MEDICAL, "high", "Medical or injury report received."
        if any(term in positive_text for term in ("wildfire", "fire", "smoke")):
            return EventType.FIRE, "moderate", "Fire or smoke observation reported."
        if any(term in positive_text for term in ("road closed", "road closure", "road is closed")):
            return EventType.ROAD_STATUS, "moderate", "Road closure reported."
        if "weather" in positive_text or any(term in positive_text for term in ("snowing", "wind", "rain", "sunny", "clear skies", "clear weather")):
            return EventType.WEATHER, None, "Weather update reported."
        if any(term in positive_text for term in ("need", "request", "send", "bring")):
            return EventType.REQUEST, None, "Operational request reported."
        if any(term in positive_text for term in ("heading", "moving", "en route", "on the way")):
            return EventType.LOCATION_UPDATE, None, "Movement or destination update reported."

        summary = original if len(original) <= 280 else original[:277].rstrip() + "..."
        return EventType.GENERAL_UPDATE, None, summary

    @classmethod
    def _keywords(cls, lowered: str) -> list[str]:
        positive_text = cls._positive_text(lowered)
        vocabulary = (
            "avalanche",
            "slide",
            "burial",
            "shooting cracks",
            "collapse",
            "mayday",
            "injury",
            "medical",
            "fire",
            "smoke",
            "road closed",
        )
        return [term for term in vocabulary if term in positive_text]

    @staticmethod
    def _confidence(
        *,
        event_type: EventType,
        callsign: str | None,
        aspect: str | None,
        elevation_ft: int | None,
        keywords: list[str],
    ) -> float:
        confidence = 0.55 if event_type == EventType.GENERAL_UPDATE else 0.72
        if keywords:
            confidence += 0.08
        if callsign:
            confidence += 0.05
        if aspect:
            confidence += 0.04
        if elevation_ft:
            confidence += 0.04
        return min(round(confidence, 2), 0.95)


class TerraEngine:
    """Provider-neutral entry point for structured operational extraction."""

    def __init__(self, provider: IntelligenceProvider | None = None) -> None:
        self.provider = provider or DeterministicIntelligenceProvider()

    async def process(
        self,
        *,
        text: str,
        callsign_hint: str | None = None,
    ) -> list[ExtractedEvent]:
        return await self.provider.extract_events(text=text, callsign_hint=callsign_hint)
