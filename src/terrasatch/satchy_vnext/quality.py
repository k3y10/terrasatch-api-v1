"""Context quality and conservative contradiction checks for Satchy vNext."""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from .schemas import ContextPacket, EvidenceClass, EvidenceRef


class QualityIssueType(StrEnum):
    STALE_EVIDENCE = "stale_evidence"
    LOW_CONFIDENCE = "low_confidence"
    CONTRADICTION = "contradiction"
    MISSING_LOCATION = "missing_location"
    MISSING_EVIDENCE = "missing_evidence"


class QualityIssue(BaseModel):
    issue_type: QualityIssueType
    severity: str = Field(pattern="^(info|warning|high)$")
    summary: str = Field(min_length=1, max_length=2000)
    evidence_ids: list[str] = Field(default_factory=list, max_length=64)
    fact_key: str | None = Field(default=None, max_length=255)


class ContextQualityReport(BaseModel):
    evidence_count: int = Field(ge=0)
    source_class_counts: dict[str, int] = Field(default_factory=dict)
    issues: list[QualityIssue] = Field(default_factory=list)
    contradiction_count: int = Field(default=0, ge=0)
    stale_count: int = Field(default=0, ge=0)
    low_confidence_count: int = Field(default=0, ge=0)

    @property
    def has_high_severity_issue(self) -> bool:
        return any(item.severity == "high" for item in self.issues)


_NON_COMPARABLE_FACTS = frozenset({"type", "source", "source_type", "callsign", "location"})


def _location_key(item: EvidenceRef) -> str:
    if not item.location:
        return ""
    return json.dumps(item.location, sort_keys=True, separators=(",", ":"), default=str)


def _normalized_scalar(value: Any) -> str | None:
    if value is None or isinstance(value, (dict, list, tuple, set)):
        return None
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value).strip().casefold()


def _contradictions(evidence: list[EvidenceRef]) -> list[QualityIssue]:
    buckets: dict[tuple[str, str], list[tuple[str, str]]] = {}
    for item in evidence:
        location = _location_key(item)
        if not location:
            continue
        for key, raw_value in item.facts.items():
            if key.casefold() in _NON_COMPARABLE_FACTS:
                continue
            value = _normalized_scalar(raw_value)
            if value is None or not value:
                continue
            buckets.setdefault((location, key), []).append((item.id, value))

    issues: list[QualityIssue] = []
    for (_location, fact_key), rows in buckets.items():
        values = {value for _evidence_id, value in rows}
        if len(values) <= 1:
            continue
        evidence_ids = [evidence_id for evidence_id, _value in rows]
        issues.append(
            QualityIssue(
                issue_type=QualityIssueType.CONTRADICTION,
                severity="high",
                summary=(
                    f"Conflicting values were supplied for '{fact_key}' at the same "
                    "normalized location."
                ),
                evidence_ids=evidence_ids,
                fact_key=fact_key,
            )
        )
    return issues


def _as_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def inspect_context_quality(
    packet: ContextPacket,
    *,
    now: datetime | None = None,
    stale_after_seconds: int = 6 * 60 * 60,
    low_confidence_threshold: float = 0.50,
) -> ContextQualityReport:
    now = _as_aware(now or datetime.now(UTC))
    issues: list[QualityIssue] = []
    stale_count = 0
    low_confidence_count = 0

    if not packet.evidence:
        issues.append(
            QualityIssue(
                issue_type=QualityIssueType.MISSING_EVIDENCE,
                severity="warning",
                summary="No evidence is available in the authorized ContextPacket.",
            )
        )

    for item in packet.evidence:
        if item.confidence < low_confidence_threshold:
            low_confidence_count += 1
            issues.append(
                QualityIssue(
                    issue_type=QualityIssueType.LOW_CONFIDENCE,
                    severity="warning",
                    summary=(
                        f"Evidence {item.id} has confidence {item.confidence:.2f}, below "
                        f"{low_confidence_threshold:.2f}."
                    ),
                    evidence_ids=[item.id],
                )
            )

        if item.observed_at is not None:
            observed_at = _as_aware(item.observed_at)
            age_seconds = max(0.0, (now - observed_at).total_seconds())
            if age_seconds > stale_after_seconds:
                stale_count += 1
                issues.append(
                    QualityIssue(
                        issue_type=QualityIssueType.STALE_EVIDENCE,
                        severity="warning",
                        summary=(
                            f"Evidence {item.id} is older than the configured freshness "
                            "threshold."
                        ),
                        evidence_ids=[item.id],
                    )
                )

    if packet.evidence and not any(item.location for item in packet.evidence):
        if not packet.spatial_context:
            issues.append(
                QualityIssue(
                    issue_type=QualityIssueType.MISSING_LOCATION,
                    severity="info",
                    summary="No evidence item or spatial context includes a resolved location.",
                    evidence_ids=[item.id for item in packet.evidence],
                )
            )

    contradiction_issues = _contradictions(packet.evidence)
    issues.extend(contradiction_issues)
    class_counts = Counter(item.evidence_class.value for item in packet.evidence)

    return ContextQualityReport(
        evidence_count=len(packet.evidence),
        source_class_counts=dict(class_counts),
        issues=issues,
        contradiction_count=len(contradiction_issues),
        stale_count=stale_count,
        low_confidence_count=low_confidence_count,
    )


def count_authoritative_sources(packet: ContextPacket) -> int:
    authoritative = {
        EvidenceClass.OBSERVED,
        EvidenceClass.OFFICIAL_PUBLISHED,
    }
    return sum(1 for item in packet.evidence if item.evidence_class in authoritative)
