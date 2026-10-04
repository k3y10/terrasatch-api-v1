"""Future TerraSatch architecture boundaries used by Satchy vNext.

These are protocols only. They deliberately do not import or reroute existing production
EchoSatch/EdgeSatch/GridSatch/CoreSatch/QuakSatch implementations.
"""

from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

from .schemas import ContextPacket, EvidenceRef


class EchoSatchClient(Protocol):
    async def search_signals(
        self,
        *,
        organization_id: UUID,
        site_id: UUID,
        query: str,
        limit: int = 20,
    ) -> list[EvidenceRef]: ...


class GridSatchClient(Protocol):
    async def resolve_context(
        self,
        *,
        organization_id: UUID,
        site_id: UUID,
        location: dict[str, Any],
    ) -> dict[str, Any]: ...


class CoreSatchClient(Protocol):
    async def enrich(self, packet: ContextPacket) -> ContextPacket: ...


class QuakSatchClient(Protocol):
    async def authorize(
        self,
        *,
        organization_id: UUID,
        user_id: UUID | None,
        resource: str,
        action: str,
    ) -> bool: ...
