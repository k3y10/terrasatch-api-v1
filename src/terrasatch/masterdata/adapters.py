"""Provider adapter contract and an independently controlled registry."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class AdapterRecord:
    """One authoritative provider record before canonical persistence."""

    provider_record_id: str
    payload: bytes
    source_url: str | None = None
    source_timestamp: datetime | None = None
    source_updated_at: datetime | None = None
    content_type: str = "application/json"
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AdapterBatch:
    """A bounded incremental adapter response."""

    records: Sequence[AdapterRecord]
    next_cursor: str | None = None
    etag: str | None = None
    last_modified: str | None = None


class SourceAdapter(Protocol):
    """Contract implemented by UAC, CAIC, weather, GIS, and future adapters."""

    key: str
    version: str

    async def fetch(
        self,
        *,
        configuration: Mapping[str, object],
        cursor: str | None,
        etag: str | None,
        last_modified: str | None,
    ) -> AdapterBatch:
        """Fetch one bounded, incremental batch without touching the Edge path."""


class AdapterRegistry:
    """Explicit adapter allow-list; each adapter can be omitted or disabled."""

    def __init__(self) -> None:
        self._adapters: dict[str, SourceAdapter] = {}

    def register(self, adapter: SourceAdapter) -> None:
        key = adapter.key.strip().lower()
        if not key:
            raise ValueError("Adapter key cannot be empty")
        if key in self._adapters:
            raise ValueError(f"Adapter already registered: {key}")
        self._adapters[key] = adapter

    def get(self, key: str) -> SourceAdapter:
        normalized = key.strip().lower()
        try:
            return self._adapters[normalized]
        except KeyError as exc:
            raise KeyError(f"Adapter is not registered: {normalized}") from exc

    def keys(self) -> tuple[str, ...]:
        return tuple(sorted(self._adapters))


class ManualSnapshotAdapter:
    """No-network adapter used for controlled raw snapshot and CSV workflows."""

    key = "manual_snapshot"
    version = "1"

    async def fetch(
        self,
        *,
        configuration: Mapping[str, object],
        cursor: str | None,
        etag: str | None,
        last_modified: str | None,
    ) -> AdapterBatch:
        del configuration, etag, last_modified
        return AdapterBatch(records=(), next_cursor=cursor)


adapters = AdapterRegistry()
adapters.register(ManualSnapshotAdapter())
