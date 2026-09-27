"""Domain profiles shared by Satchy vNext.

Profiles add vocabulary and safety constraints; they never replace authoritative forecasts,
incident command, agency policy, or a qualified human decision maker.
"""

from __future__ import annotations

from dataclasses import dataclass

from .schemas import DomainProfile, EvidenceClass


@dataclass(frozen=True, slots=True)
class DomainDefinition:
    profile: DomainProfile
    purpose: str
    keywords: tuple[str, ...]
    preferred_fields: tuple[str, ...]
    safety_rules: tuple[str, ...]
    evidence_precedence: tuple[EvidenceClass, ...]


_DEFAULT_PRECEDENCE = (
    EvidenceClass.OBSERVED,
    EvidenceClass.OFFICIAL_PUBLISHED,
    EvidenceClass.MODELED,
    EvidenceClass.DERIVED,
    EvidenceClass.USER_PROVIDED,
    EvidenceClass.AI_INTERPRETED,
)


DOMAIN_DEFINITIONS: dict[DomainProfile, DomainDefinition] = {
    DomainProfile.GENERAL: DomainDefinition(
        profile=DomainProfile.GENERAL,
        purpose="Cross-domain field operations and incident context.",
        keywords=(),
        preferred_fields=("location", "time", "source", "status"),
        safety_rules=(
            "Do not convert incomplete context into operational fact.",
            "Separate observations, published information, model output, and AI interpretation.",
        ),
        evidence_precedence=_DEFAULT_PRECEDENCE,
    ),
    DomainProfile.AVY: DomainDefinition(
        profile=DomainProfile.AVY,
        purpose="Avalanche, snowpack, terrain, and winter field intelligence.",
        keywords=(
            "avalanche", "snowpack", "slab", "cornice", "whumpf", "shooting cracks",
            "snotel", "snowpit", "aspect", "slope", "wind slab", "persistent weak layer",
        ),
        preferred_fields=(
            "location", "aspect", "elevation_ft", "slope_angle", "trigger", "size",
            "avalanche_problem", "involvement", "snowpack_test",
        ),
        safety_rules=(
            "Never declare terrain safe from an absence of observations.",
            "Treat an official avalanche forecast as published guidance, not a field observation.",
            "Preserve negative findings such as no avalanche activity without flipping polarity.",
        ),
        evidence_precedence=_DEFAULT_PRECEDENCE,
    ),
    DomainProfile.PYRO: DomainDefinition(
        profile=DomainProfile.PYRO,
        purpose="Wildfire, smoke, fuels, weather, and response intelligence.",
        keywords=(
            "wildfire", "fire", "smoke", "flame", "hotspot", "red flag", "fuels",
            "perimeter", "containment", "evacuation",
        ),
        preferred_fields=(
            "location", "perimeter", "acres", "containment", "wind", "humidity",
            "fuel", "spread_direction", "evacuation_status",
        ),
        safety_rules=(
            "Do not issue evacuation orders or incident-command instructions.",
            "Distinguish official perimeter/status data from inferred fire behavior.",
        ),
        evidence_precedence=_DEFAULT_PRECEDENCE,
    ),
    DomainProfile.HYDRO: DomainDefinition(
        profile=DomainProfile.HYDRO,
        purpose="Watershed, flood, streamflow, runoff, and water intelligence.",
        keywords=(
            "flood", "stream", "river", "flow", "gauge", "runoff", "watershed",
            "snow water equivalent", "swe", "stage",
        ),
        preferred_fields=(
            "location", "gauge_id", "stage", "flow", "trend", "snow_water_equivalent",
            "precipitation", "warning_status",
        ),
        safety_rules=(
            "Keep observed gauge values distinct from modeled flood projections.",
            "Do not represent a model threshold crossing as an official warning unless sourced as one.",
        ),
        evidence_precedence=_DEFAULT_PRECEDENCE,
    ),
    DomainProfile.GEO: DomainDefinition(
        profile=DomainProfile.GEO,
        purpose="Geohazard, slope stability, rockfall, landslide, and terrain intelligence.",
        keywords=(
            "landslide", "rockfall", "debris flow", "slope stability", "fault",
            "subsidence", "erosion", "geology",
        ),
        preferred_fields=(
            "location", "movement", "material", "slope_angle", "trigger", "asset_exposure",
        ),
        safety_rules=(
            "Do not infer engineering stability from a single observation.",
            "Keep measured deformation separate from AI interpretation.",
        ),
        evidence_precedence=_DEFAULT_PRECEDENCE,
    ),
    DomainProfile.INFRA: DomainDefinition(
        profile=DomainProfile.INFRA,
        purpose="Remote asset, utility, route, communications, and infrastructure intelligence.",
        keywords=(
            "infrastructure", "asset", "tower", "repeater", "utility", "road", "bridge",
            "outage", "equipment", "sensor",
        ),
        preferred_fields=(
            "asset_id", "location", "status", "telemetry", "last_seen", "failure_mode",
        ),
        safety_rules=(
            "Do not command physical equipment without the existing TerraSatch approval path.",
            "Treat stale telemetry as stale, not current state.",
        ),
        evidence_precedence=_DEFAULT_PRECEDENCE,
    ),
}


def infer_domain(text: str) -> DomainProfile:
    lowered = text.casefold()
    scores: dict[DomainProfile, int] = {profile: 0 for profile in DOMAIN_DEFINITIONS}
    for profile, definition in DOMAIN_DEFINITIONS.items():
        for keyword in definition.keywords:
            if keyword in lowered:
                scores[profile] += 1
    best = max(scores, key=scores.get)
    return best if scores[best] else DomainProfile.GENERAL


def definition_for(profile: DomainProfile) -> DomainDefinition:
    return DOMAIN_DEFINITIONS[profile]
