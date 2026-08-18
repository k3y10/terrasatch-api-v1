"""Trusted spatial grounding for model-extracted field locations."""

from __future__ import annotations

import re
from typing import Protocol

from pydantic import BaseModel, Field

from .core import ExtractedEvent


class KnownLocation(BaseModel):
    name: str
    aliases: list[str] = Field(default_factory=list)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    cell_id: str | None = None
    zone_id: str | None = None


class SpatialResolution(BaseModel):
    matched: bool
    query: str | None = None
    name: str | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    cell_id: str | None = None
    zone_id: str | None = None
    source: str = "configured_catalog"
    confidence: float = Field(default=0, ge=0, le=1)


class SpatialResolver(Protocol):
    def resolve(self, location_text: str | None) -> SpatialResolution: ...


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


class ConfiguredSpatialResolver:
    """Exact/alias resolver for partner-owned site gazetteers and cell catalogs."""

    def __init__(self, locations: list[KnownLocation]) -> None:
        self._index: dict[str, KnownLocation] = {}
        for location in locations:
            keys = [location.name, *location.aliases]
            for key in keys:
                normalized = _normalize(key)
                if normalized:
                    self._index[normalized] = location

    def resolve(self, location_text: str | None) -> SpatialResolution:
        if not location_text or not location_text.strip():
            return SpatialResolution(matched=False, query=location_text)
        query = location_text.strip()
        match = self._index.get(_normalize(query))
        if match is None:
            return SpatialResolution(matched=False, query=query)
        return SpatialResolution(
            matched=True,
            query=query,
            name=match.name,
            latitude=match.latitude,
            longitude=match.longitude,
            cell_id=match.cell_id,
            zone_id=match.zone_id,
            confidence=1.0,
        )

    def ground_event(self, event: ExtractedEvent) -> ExtractedEvent:
        resolution = self.resolve(event.location_text)
        data = dict(event.data)
        data["spatial"] = resolution.model_dump()
        if not resolution.matched:
            return event.model_copy(update={"data": data})
        return event.model_copy(
            update={
                "latitude": resolution.latitude,
                "longitude": resolution.longitude,
                "data": data,
            }
        )
