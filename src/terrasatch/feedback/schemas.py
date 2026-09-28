"""Validated payloads for TerraSatch native feedback and first-party attribution."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_DISTRIBUTION_RE = re.compile(r"^[A-Z0-9][A-Z0-9_-]{0,99}$")
_QUESTION_ID_RE = re.compile(r"^[a-z0-9_]{1,64}$")

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

ActivityContext = Literal[
    "backcountry_snow",
    "hiking_climbing",
    "biking_trail",
    "hunting_fishing",
    "camping_overland",
    "ski_patrol_avalanche",
    "sar_emergency",
    "guiding_outdoor_ops",
    "land_wildfire_watershed",
    "utilities_infrastructure",
    "research_inspection",
    "mixed_outdoor",
    "other",
]
Tool = Literal[
    "phone_apps",
    "radio",
    "gps_watch",
    "satellite",
    "paper_notes",
    "camera",
    "other",
]


class SurveyResponseCreate(BaseModel):
    """One adaptive, anonymous-by-default customer-discovery response."""

    model_config = ConfigDict(extra="forbid")

    distribution_id: str = Field(default="DIRECT", min_length=1, max_length=100)
    audience: Literal["recreation", "work", "both"]
    activity_context: ActivityContext
    tools: list[Tool] = Field(min_length=1, max_length=7)
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
    tool_follow_up: str | None = Field(default=None, max_length=64)
    pain_follow_up: str | None = Field(default=None, max_length=64)
    time_burden: Literal[
        "under_15m",
        "15_30m",
        "30_60m",
        "1_2h",
        "2h_plus",
        "not_sure",
    ] | None = None
    spend_band: str = Field(min_length=2, max_length=32)
    concept_interest: Literal["definitely", "would_try", "maybe", "probably_not"]
    questions_shown: list[str] = Field(min_length=7, max_length=16)
    started_at: datetime
    completion_seconds: int = Field(ge=5, le=3600)
    comment: str | None = Field(default=None, max_length=1000)

    @field_validator("distribution_id")
    @classmethod
    def normalize_distribution(cls, value: str) -> str:
        normalized = value.strip().upper()
        return normalized if _DISTRIBUTION_RE.fullmatch(normalized) else "DIRECT"

    @field_validator("tools")
    @classmethod
    def normalize_tools(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(value))

    @field_validator("questions_shown")
    @classmethod
    def normalize_questions_shown(cls, value: list[str]) -> list[str]:
        normalized = list(dict.fromkeys(item.strip() for item in value if item.strip()))
        if any(not _QUESTION_ID_RE.fullmatch(item) for item in normalized):
            raise ValueError("Question IDs must use lowercase letters, numbers, or underscores")
        return normalized

    @field_validator("comment", "tool_follow_up", "pain_follow_up")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def validate_adaptive_path(self):
        allowed_spend = PERSONAL_SPEND if self.audience == "recreation" else TEAM_SPEND
        if self.spend_band not in allowed_spend:
            raise ValueError("Spend band does not match the selected audience")

        required_questions = {
            "audience",
            "activity_context",
            "tools",
            "connectivity",
            "primary_hassle",
            "spend_band",
            "concept_interest",
        }
        if not required_questions.issubset(set(self.questions_shown)):
            raise ValueError("Adaptive response is missing required question IDs")

        needs_tool_follow_up = "radio" in self.tools or "satellite" in self.tools
        if needs_tool_follow_up and not self.tool_follow_up:
            raise ValueError("Selected tools require a tool follow-up")
        if needs_tool_follow_up and "tool_follow_up" not in self.questions_shown:
            raise ValueError("Tool follow-up was not recorded as shown")

        needs_pain_follow_up = self.primary_hassle != "nothing_major"
        if needs_pain_follow_up and not self.pain_follow_up:
            raise ValueError("Selected friction requires a pain follow-up")
        if needs_pain_follow_up and "pain_follow_up" not in self.questions_shown:
            raise ValueError("Pain follow-up was not recorded as shown")

        if self.audience in {"work", "both"}:
            if not self.time_burden:
                raise ValueError("Field-work responses require current time burden")
            if "time_burden" not in self.questions_shown:
                raise ValueError("Time-burden question was not recorded as shown")
        elif self.time_burden is not None:
            raise ValueError("Recreation-only responses must not include team time burden")

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
