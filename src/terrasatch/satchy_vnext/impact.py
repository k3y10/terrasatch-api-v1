"""Measured customer-impact metrics for Satchy trials and production reviews."""

from __future__ import annotations

from datetime import datetime
from statistics import mean
from uuid import UUID

from pydantic import BaseModel, Field

from .schemas import utcnow


class ImpactMeasurement(BaseModel):
    """One measured workflow comparison.

    Values should come from observed/manual baselines or reviewed workflow timings. Satchy should
    never manufacture a baseline merely to claim savings.
    """

    run_id: UUID | None = None
    workflow: str = Field(min_length=1, max_length=255)
    manual_seconds: float = Field(ge=0)
    assisted_seconds: float = Field(ge=0)
    accepted: bool | None = None
    edit_ratio: float | None = Field(default=None, ge=0, le=1)
    source_record_count: int = Field(default=0, ge=0)
    notes: str | None = Field(default=None, max_length=2000)
    measured_at: datetime = Field(default_factory=utcnow)

    @property
    def seconds_saved(self) -> float:
        return max(0.0, self.manual_seconds - self.assisted_seconds)

    @property
    def percent_saved(self) -> float | None:
        if self.manual_seconds <= 0:
            return None
        return min(1.0, self.seconds_saved / self.manual_seconds)


class ImpactSummary(BaseModel):
    measurement_count: int = Field(ge=0)
    measured_manual_minutes: float = Field(ge=0)
    measured_assisted_minutes: float = Field(ge=0)
    measured_minutes_saved: float = Field(ge=0)
    acceptance_rate: float | None = Field(default=None, ge=0, le=1)
    mean_edit_ratio: float | None = Field(default=None, ge=0, le=1)
    source_record_count: int = Field(ge=0)
    workflows: dict[str, int] = Field(default_factory=dict)


def summarize_impact(measurements: list[ImpactMeasurement]) -> ImpactSummary:
    workflow_counts: dict[str, int] = {}
    accepted_values: list[float] = []
    edit_ratios: list[float] = []
    for item in measurements:
        workflow_counts[item.workflow] = workflow_counts.get(item.workflow, 0) + 1
        if item.accepted is not None:
            accepted_values.append(1.0 if item.accepted else 0.0)
        if item.edit_ratio is not None:
            edit_ratios.append(item.edit_ratio)

    manual_seconds = sum(item.manual_seconds for item in measurements)
    assisted_seconds = sum(item.assisted_seconds for item in measurements)
    saved_seconds = sum(item.seconds_saved for item in measurements)

    return ImpactSummary(
        measurement_count=len(measurements),
        measured_manual_minutes=round(manual_seconds / 60.0, 2),
        measured_assisted_minutes=round(assisted_seconds / 60.0, 2),
        measured_minutes_saved=round(saved_seconds / 60.0, 2),
        acceptance_rate=round(mean(accepted_values), 4) if accepted_values else None,
        mean_edit_ratio=round(mean(edit_ratios), 4) if edit_ratios else None,
        source_record_count=sum(item.source_record_count for item in measurements),
        workflows=workflow_counts,
    )
