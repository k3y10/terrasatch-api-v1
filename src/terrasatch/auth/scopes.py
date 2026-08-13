"""Stable service-credential scopes supported by the TerraSatch API."""

from __future__ import annotations

SUPPORTED_API_SCOPES = frozenset(
    {
        "admin",
        "edge:ingest",
        "read:sites",
        "write:sites",
        "read:teams",
        "write:teams",
        "read:agents",
        "write:agents",
        "read:channels",
        "write:channels",
        "read:callsigns",
        "write:callsigns",
        "read:transmissions",
        "read:transcripts",
        "read:events",
    }
)


def validate_api_scopes(scopes: set[str]) -> list[str]:
    """Return normalized supported scopes or raise for an unknown/empty scope set."""

    from terrasatch.errors import InvalidConfiguration

    normalized = {scope.strip() for scope in scopes if scope.strip()}
    if not normalized:
        raise InvalidConfiguration("At least one API scope is required")
    unknown = sorted(normalized - SUPPORTED_API_SCOPES)
    if unknown:
        raise InvalidConfiguration(
            "Unsupported API scope(s): " + ", ".join(unknown),
            details={"supported_scopes": sorted(SUPPORTED_API_SCOPES)},
        )
    return sorted(normalized)
