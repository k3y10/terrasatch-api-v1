"""Bounded, non-operational user adaptation signals for Satchy."""

from __future__ import annotations

from uuid import UUID

from terrasatch.satchy.schemas import ActiveMapContext
from terrasatch.workspace.models import WorkspacePreference

_MAX_KEYS = 32
_MAX_COUNT = 10_000


def _increment(bucket: dict[str, object], key: str | None) -> None:
    normalized = key.strip() if isinstance(key, str) and key.strip() else None
    if normalized is None:
        return
    if normalized not in bucket and len(bucket) >= _MAX_KEYS:
        return
    current = bucket.get(normalized, 0)
    count = current if isinstance(current, int) and current >= 0 else 0
    bucket[normalized] = min(count + 1, _MAX_COUNT)


def observe_workspace_context(
    preference: WorkspacePreference,
    *,
    site_id: UUID,
    active_map: ActiveMapContext | None,
) -> None:
    """Record UX/workflow usage only; never persist map coordinates or operational claims."""

    profile = dict(preference.satchy_preferences or {})
    observed_raw = profile.get("observed")
    observed = dict(observed_raw) if isinstance(observed_raw, dict) else {}

    site_counts_raw = observed.get("site_counts")
    site_counts = dict(site_counts_raw) if isinstance(site_counts_raw, dict) else {}
    _increment(site_counts, str(site_id))
    observed["site_counts"] = site_counts

    if active_map is not None:
        map_counts_raw = observed.get("map_counts")
        map_counts = dict(map_counts_raw) if isinstance(map_counts_raw, dict) else {}
        _increment(map_counts, active_map.map_id)
        observed["map_counts"] = map_counts

        layer_counts_raw = observed.get("layer_counts")
        layer_counts = dict(layer_counts_raw) if isinstance(layer_counts_raw, dict) else {}
        for layer in active_map.selected_layers:
            _increment(layer_counts, layer)
        observed["layer_counts"] = layer_counts

    profile["observed"] = observed
    preference.satchy_preferences = profile
