"""Shared workspace/runtime contracts used by UI, Satchy, demos, and Edge."""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.edge.models import EdgeDevice
from terrasatch.workspace.models import WorkspaceProfile


class WorkspaceRuntimeMode(StrEnum):
    """Internal rollout modes for Satchy intelligence."""

    LEGACY = "legacy"
    SHADOW = "shadow"
    AGENT_READ = "agent_read"
    AGENT_PROPOSE = "agent_propose"


class DiscoveryStatus(StrEnum):
    """Customer-facing lifecycle for the 14-day Satchy Discovery."""

    NOT_STARTED = "not_started"
    ACTIVE = "active"
    COMPLETE = "complete"
    INTEGRATED = "integrated"


class DiscoveryPhaseState(StrEnum):
    OFF = "off"
    ACTIVE = "active"
    TESTING = "testing"
    READY = "ready"


DISCOVERY_DURATION_DAYS = 14
_DISCOVERY_PHASES = ("listen", "watch", "learn", "adapt")
_DISCOVERY_WORKFLOW_COUNTS = ("identified", "testing", "approved")


def discovery_state_for_status(
    status: DiscoveryStatus | str,
    *,
    day: int | None = None,
) -> dict[str, object]:
    """Return the default LISTEN/WATCH/LEARN/ADAPT state for one lifecycle status."""

    normalized_status = DiscoveryStatus(status)
    if normalized_status == DiscoveryStatus.NOT_STARTED:
        normalized_day = 0
        phases = {phase: DiscoveryPhaseState.OFF.value for phase in _DISCOVERY_PHASES}
    elif normalized_status == DiscoveryStatus.ACTIVE:
        normalized_day = min(DISCOVERY_DURATION_DAYS, max(1, day or 1))
        phases = {
            "listen": DiscoveryPhaseState.ACTIVE.value,
            "watch": DiscoveryPhaseState.ACTIVE.value,
            "learn": DiscoveryPhaseState.ACTIVE.value,
            "adapt": DiscoveryPhaseState.TESTING.value,
        }
    elif normalized_status == DiscoveryStatus.COMPLETE:
        normalized_day = DISCOVERY_DURATION_DAYS
        phases = {
            "listen": DiscoveryPhaseState.ACTIVE.value,
            "watch": DiscoveryPhaseState.ACTIVE.value,
            "learn": DiscoveryPhaseState.ACTIVE.value,
            "adapt": DiscoveryPhaseState.READY.value,
        }
    else:
        normalized_day = DISCOVERY_DURATION_DAYS
        phases = {phase: DiscoveryPhaseState.ACTIVE.value for phase in _DISCOVERY_PHASES}

    return {
        "status": normalized_status.value,
        "duration_days": DISCOVERY_DURATION_DAYS,
        "day": normalized_day,
        "phases": phases,
        "workflow_counts": {
            "identified": 0,
            "testing": 0,
            "approved": 0,
        },
    }


DEFAULT_DISCOVERY_STATE: dict[str, object] = discovery_state_for_status(
    DiscoveryStatus.NOT_STARTED
)


def normalize_discovery_state(value: dict[str, object] | None) -> dict[str, object]:
    """Normalize persisted JSON into the stable customer-facing Discovery contract."""

    raw = dict(value or {})
    raw_status = raw.get("status")
    try:
        status = DiscoveryStatus(str(raw_status or DiscoveryStatus.NOT_STARTED.value))
    except ValueError:
        status = DiscoveryStatus.NOT_STARTED

    raw_day = raw.get("day")
    day = raw_day if isinstance(raw_day, int) else None
    normalized = discovery_state_for_status(status, day=day)

    raw_phases = raw.get("phases")
    if isinstance(raw_phases, dict):
        phases = dict(normalized["phases"])
        for phase in _DISCOVERY_PHASES:
            candidate = raw_phases.get(phase)
            if candidate in {item.value for item in DiscoveryPhaseState}:
                phases[phase] = candidate
        normalized["phases"] = phases

    raw_counts = raw.get("workflow_counts")
    if isinstance(raw_counts, dict):
        counts = dict(normalized["workflow_counts"])
        for key in _DISCOVERY_WORKFLOW_COUNTS:
            candidate = raw_counts.get(key)
            if isinstance(candidate, int) and candidate >= 0:
                counts[key] = candidate
        normalized["workflow_counts"] = counts

    return normalized


def update_discovery_state(
    current: dict[str, object] | None,
    *,
    status: str | None = None,
    day: int | None = None,
    phase_updates: dict[str, str] | None = None,
    workflow_count_updates: dict[str, int] | None = None,
) -> dict[str, object]:
    """Apply an explicit admin update without conflating Discovery with runtime shadowing."""

    existing = normalize_discovery_state(current)
    next_status = DiscoveryStatus(status or str(existing["status"]))

    if status is not None and status != existing["status"]:
        updated = discovery_state_for_status(next_status, day=day)
        updated["workflow_counts"] = dict(existing["workflow_counts"])
    else:
        updated = normalize_discovery_state(existing)
        if day is not None:
            if next_status == DiscoveryStatus.ACTIVE:
                updated["day"] = min(DISCOVERY_DURATION_DAYS, max(1, day))
            elif next_status == DiscoveryStatus.NOT_STARTED:
                updated["day"] = 0
            else:
                updated["day"] = DISCOVERY_DURATION_DAYS

    if phase_updates:
        phases = dict(updated["phases"])
        phases.update(phase_updates)
        updated["phases"] = phases

    if workflow_count_updates:
        counts = dict(updated["workflow_counts"])
        counts.update(workflow_count_updates)
        updated["workflow_counts"] = counts

    return normalize_discovery_state(updated)


def _is_physical_edge_capability(capability: str) -> bool:
    normalized = capability.strip().lower()
    return any(
        token in normalized
        for token in (":transmit", ".transmit", "mission", "command", "actuate")
    )


def workspace_profile_payload(profile: WorkspaceProfile | None) -> dict[str, object]:
    """Return a stable profile contract even before an organization customizes it."""

    if profile is None:
        return {
            "operational_domain": "general",
            "workspace_template": "general",
            "runtime_mode": WorkspaceRuntimeMode.LEGACY.value,
            "recommended_modules": [],
            "preferred_map_layers": [],
            "workflow_preferences": [],
            "discovery_state": normalize_discovery_state(None),
        }

    return {
        "operational_domain": profile.operational_domain,
        "workspace_template": profile.workspace_template,
        "runtime_mode": profile.runtime_mode,
        "recommended_modules": list(profile.recommended_modules or []),
        "preferred_map_layers": list(profile.preferred_map_layers or []),
        "workflow_preferences": list(profile.workflow_preferences or []),
        "discovery_state": normalize_discovery_state(profile.discovery_state),
    }


async def get_workspace_profile(
    session: AsyncSession,
    *,
    organization_id: UUID,
) -> WorkspaceProfile | None:
    return await session.get(WorkspaceProfile, organization_id)


async def get_or_create_workspace_profile(
    session: AsyncSession,
    *,
    organization_id: UUID,
) -> WorkspaceProfile:
    profile = await session.get(WorkspaceProfile, organization_id)
    if profile is None:
        profile = WorkspaceProfile(
            organization_id=organization_id,
            operational_domain="general",
            workspace_template="general",
            runtime_mode=WorkspaceRuntimeMode.LEGACY.value,
            recommended_modules=[],
            preferred_map_layers=[],
            workflow_preferences=[],
            discovery_state=normalize_discovery_state(None),
        )
        session.add(profile)
        await session.flush()
    return profile


def build_capability_manifest(
    *,
    profile: WorkspaceProfile | None,
    catalog: list[dict[str, object]],
    devices: list[EdgeDevice],
) -> dict[str, object]:
    """Build one capability truth for workspace clients and Satchy.

    Provider capabilities only become available when the provider is both
    connected and runtime-ready. Edge capabilities come only from enabled
    devices reporting them. Consequential/physical actions remain approval-gated.
    """

    profile_data = workspace_profile_payload(profile)
    runtime_mode = str(profile_data["runtime_mode"])

    read_capabilities: set[str] = set()
    write_capabilities: set[str] = set()
    connected_providers: set[str] = set()

    for provider in catalog:
        if not provider.get("connected") or not provider.get("runtime_ready"):
            continue
        key = provider.get("key")
        if isinstance(key, str):
            connected_providers.add(key)
        for detail in provider.get("capability_details") or []:
            if not isinstance(detail, dict):
                continue
            capability = detail.get("key")
            access = detail.get("access")
            if not isinstance(capability, str):
                continue
            if access == "read":
                read_capabilities.add(capability)
            elif access == "write":
                write_capabilities.add(capability)

    edge_devices = []
    edge_capabilities: set[str] = set()
    physical_capabilities: set[str] = set()
    for device in devices:
        if not device.enabled:
            continue
        capabilities = sorted(set(device.capabilities or []))
        edge_capabilities.update(capabilities)
        physical_capabilities.update(
            capability
            for capability in capabilities
            if _is_physical_edge_capability(capability)
        )
        edge_devices.append(
            {
                "id": str(device.id),
                "site_id": str(device.site_id),
                "name": device.name,
                "agent_version": device.agent_version,
                "capabilities": capabilities,
                "last_seen_at": (
                    device.last_seen_at.isoformat() if device.last_seen_at else None
                ),
            }
        )

    return {
        "runtime_mode": runtime_mode,
        "read": sorted(read_capabilities),
        "write": sorted(write_capabilities),
        "edge": sorted(edge_capabilities),
        "physical": sorted(physical_capabilities),
        "connected_providers": sorted(connected_providers),
        "edge_devices": edge_devices,
        "policy": {
            "agent_reads_enabled": runtime_mode
            in {
                WorkspaceRuntimeMode.AGENT_READ.value,
                WorkspaceRuntimeMode.AGENT_PROPOSE.value,
            },
            "agent_proposals_enabled": runtime_mode
            == WorkspaceRuntimeMode.AGENT_PROPOSE.value,
            "shadow_only": runtime_mode == WorkspaceRuntimeMode.SHADOW.value,
            "consequential_actions_require_approval": True,
            "physical_actions_require_approval": True,
        },
    }
