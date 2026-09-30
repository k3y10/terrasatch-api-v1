"""Shared workspace/runtime contracts used by UI, Satchy, demos, and Edge."""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.edge.models import EdgeDevice
from terrasatch.workspace.models import WorkspaceProfile


class WorkspaceRuntimeMode(StrEnum):
    """Controlled rollout modes for Satchy workspace intelligence."""

    LEGACY = "legacy"
    SHADOW = "shadow"
    AGENT_READ = "agent_read"
    AGENT_PROPOSE = "agent_propose"


DEFAULT_DISCOVERY_STATE: dict[str, object] = {"status": "not_started"}


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
            "discovery_state": dict(DEFAULT_DISCOVERY_STATE),
        }

    discovery_state = dict(profile.discovery_state or {})
    discovery_state.setdefault("status", "not_started")
    return {
        "operational_domain": profile.operational_domain,
        "workspace_template": profile.workspace_template,
        "runtime_mode": profile.runtime_mode,
        "recommended_modules": list(profile.recommended_modules or []),
        "preferred_map_layers": list(profile.preferred_map_layers or []),
        "workflow_preferences": list(profile.workflow_preferences or []),
        "discovery_state": discovery_state,
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
            discovery_state=dict(DEFAULT_DISCOVERY_STATE),
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
    physical_capabilities: set[str] = set()
    for device in devices:
        if not device.enabled:
            continue
        capabilities = sorted(set(device.capabilities or []))
        physical_capabilities.update(capabilities)
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
