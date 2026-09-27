"""Compatibility helpers from the current Satchy context into vNext contracts.

These helpers are additive only. Production routes do not import them.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from terrasatch.satchy.schemas import SatchyContext

from .schemas import (
    Connectivity,
    ContextPacket,
    DomainProfile,
    EvidenceClass,
    EvidenceRef,
)


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _evidence_class(item: dict[str, Any]) -> EvidenceClass:
    source_type = str(item.get("type") or "").casefold()
    if source_type == "source_transmission":
        return EvidenceClass.OBSERVED
    if source_type in {"official_forecast", "official_notice"}:
        return EvidenceClass.OFFICIAL_PUBLISHED
    return EvidenceClass.DERIVED


def context_packet_from_current(
    context: SatchyContext,
    *,
    domain: DomainProfile = DomainProfile.GENERAL,
    connectivity: Connectivity = Connectivity.ONLINE,
) -> ContextPacket:
    evidence: list[EvidenceRef] = []
    for raw in context.evidence:
        item = dict(raw)
        item_id = item.get("id")
        summary = item.get("summary")
        if not isinstance(item_id, str) or not item_id:
            continue
        if not isinstance(summary, str) or not summary.strip():
            continue

        facts: dict[str, Any] = {}
        for key in ("type", "callsign", "location"):
            value = item.get(key)
            if value is not None:
                facts[key] = value

        location: dict[str, Any] = {}
        raw_location = item.get("location")
        if isinstance(raw_location, str) and raw_location.strip():
            location["text"] = raw_location.strip()

        confidence = item.get("confidence")
        evidence.append(
            EvidenceRef(
                id=item_id,
                evidence_class=_evidence_class(item),
                source_type=str(item.get("type") or "unknown"),
                summary=summary.strip(),
                facts=facts,
                confidence=(
                    float(confidence)
                    if isinstance(confidence, (int, float))
                    else 1.0
                ),
                observed_at=_parse_datetime(item.get("created_at")),
                location=location,
            )
        )

    spatial_context: dict[str, Any] = {}
    if context.active_map is not None:
        spatial_context["active_map"] = context.active_map.model_dump(mode="json")

    operational_context = {
        "organization_name": context.organization_name,
        "site_name": context.site_name,
        "membership_role": context.membership_role,
        "callsign": context.callsign,
        "workspace_modules": list(context.workspace_modules),
        "operational_profile": dict(context.operational_profile),
        "edge_context": dict(context.edge_context),
        "rf_context": dict(context.rf_context),
    }

    return ContextPacket(
        organization_id=context.organization_id,
        site_id=context.site_id,
        user_id=context.user_id,
        team_id=context.team_id,
        objective=context.objective,
        domain=domain,
        connectivity=connectivity,
        evidence=evidence,
        spatial_context=spatial_context,
        operational_context=operational_context,
        user_preferences=dict(context.user_preferences),
        policy_context={
            "source": "current_satchy_context_bridge",
            "proposal_only": True,
        },
    )
