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
