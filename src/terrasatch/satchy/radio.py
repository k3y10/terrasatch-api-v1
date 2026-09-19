"""Concise radio rendering for Satchy decisions."""

from __future__ import annotations


def radio_prefix(callsign: str | None) -> str:
    caller = callsign.strip() if callsign and callsign.strip() else None
    return f"{caller}, Satchy. Copy." if caller else "Satchy copies."


def observation_logged(
    *,
    callsign: str | None,
    location: str | None = None,
    detail: str | None = None,
) -> str:
    parts = [radio_prefix(callsign)]
    if location:
        parts.append(location.strip().rstrip(".") + ".")
    if detail:
        parts.append(detail.strip().rstrip(".") + ".")
    parts.append("Field observation logged.")
    return " ".join(parts)


def clarification(callsign: str | None, field: str) -> str:
    caller = f"{callsign.strip()}, " if callsign and callsign.strip() else ""
    return f"{caller}Satchy. Copy. Say {field.strip()} again."


def action_ready(callsign: str | None, summary: str) -> str:
    return f"{radio_prefix(callsign)} {summary.strip().rstrip('.')}. Confirm."


def mission_ready(callsign: str | None, asset_name: str, objective: str) -> str:
    return (
        f"{radio_prefix(callsign)} {asset_name} is available for "
        f"{objective.strip().rstrip('.')}. Mission ready. Confirm deployment."
    )



def summary_response(
    callsign: str | None,
    *,
    count: int,
    summaries: list[str],
    location: str | None = None,
) -> str:
    """Render a compact source-backed operational summary for RF."""

    scope = f" for {location.strip()}" if location and location.strip() else ""
    if count <= 0:
        return f"{radio_prefix(callsign)} No related field reports{scope}."
    lead = f"{count} related report{'s' if count != 1 else ''}{scope}."
    details = " ".join(
        item.strip().rstrip(".") + "."
        for item in summaries[:3]
        if item and item.strip()
    )
    return f"{radio_prefix(callsign)} {lead} {details}".strip()


def mission_status_response(
    callsign: str | None,
    *,
    asset_name: str,
    status: str,
    objective: str | None = None,
) -> str:
    """Render one unambiguous field-mission state without inventing telemetry."""

    detail = f" {objective.strip().rstrip('.')}." if objective and objective.strip() else ""
    return (
        f"{radio_prefix(callsign)} {asset_name.strip()} mission is "
        f"{status.strip().replace('_', ' ')}.{detail}"
    ).strip()
