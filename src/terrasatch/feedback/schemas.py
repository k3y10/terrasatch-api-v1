"""Validated payloads for the TerraSatch native feedback flow."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

_SOURCE_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,99}$")

PERSONAL_SPEND = {"zero", "under_50", "50_99", "100_249", "250_499", "500_plus", "not_sure"}
TEAM_SPEND = {"under_1k", "1k_5k", "5k_10k", "10k_25k", "25k_50k", "50k_plus", "not_sure"}


class SurveyResponseCreate(BaseModel):
    source_code: str = Field(default="direct", min_length=1, max_length=100)
    audience: Literal["recreation", "work", "both"]
    primary_tool: Literal["phone_apps", "radio", "gps_watch", "satellite", "paper_notes", "other"]
    primary_hassle: Literal[
        "losing_service",
        "locations",
        "recording",
        "updating_others",
        "switching_apps",
        "finding_later",
        "nothing_major",
        "other",
    ]
    connectivity: Literal["often", "sometimes", "rarely", "never"]
    spend_band: str = Field(min_length=2, max_length=32)
    concept_interest: Literal["definitely", "would_try", "maybe", "probably_not"]
    comment: str | None = Field(default=None, max_length=1000)

    @field_validator("source_code")
    @classmethod
    def normalize_source(cls, value: str) -> str:
        normalized = value.strip().casefold()
        return normalized if _SOURCE_RE.fullmatch(normalized) else "direct"

    @field_validator("comment")
    @classmethod
    def normalize_comment(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def validate_spend(self):
        allowed = PERSONAL_SPEND if self.audience == "recreation" else TEAM_SPEND
        if self.spend_band not in allowed:
            raise ValueError("Spend band does not match the selected audience")
        return self
