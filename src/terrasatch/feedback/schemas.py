"""Validated payloads for TerraSatch native feedback and first-party attribution."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

_DISTRIBUTION_RE = re.compile(r"^[A-Z0-9][A-Z0-9_-]{0,99}$")

PERSONAL_SPEND = {
    "zero",
    "under_50",
    "50_99",
    "100_249",
    "250_499",
    "500_plus",
    "not_sure",
}
TEAM_SPEND = {
    "under_1k",
    "1k_5k",
    "5k_10k",
    "10k_25k",
    "25k_50k",
    "50k_plus",
    "not_sure",
}


class SurveyResponseCreate(BaseModel):
    distribution_id: str = Field(default="DIRECT", min_length=1, max_length=100)
    audience: Literal["recreation", "work", "both"]
    primary_tool: Literal[
        "phone_apps",
        "radio",
        "gps_watch",
        "satellite",
        "paper_notes",
        "other",
    ]
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

    @field_validator("distribution_id")
    @classmethod
    def normalize_distribution(cls, value: str) -> str:
        normalized = value.strip().upper()
        return normalized if _DISTRIBUTION_RE.fullmatch(normalized) else "DIRECT"

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


class DistributionCreate(BaseModel):
    distribution_id: str = Field(min_length=1, max_length=100)
    label: str = Field(min_length=1, max_length=255)
    channel: Literal["direct", "qr", "print", "event", "social", "email", "partner", "other"]
    placement: str | None = Field(default=None, max_length=255)
    audience_hint: str | None = Field(default=None, max_length=64)
    metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("distribution_id")
    @classmethod
    def normalize_distribution(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not _DISTRIBUTION_RE.fullmatch(normalized):
            raise ValueError("Use only letters, numbers, hyphens, or underscores")
        if normalized == "DIRECT":
            raise ValueError("DIRECT is reserved for unattributed responses")
        return normalized

    @field_validator("label", "placement", "audience_hint")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None
