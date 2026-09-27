"""Scoped memory contracts for Satchy vNext.

Memory is opt-in and evidence-linked. Operational facts should remain in canonical TerraSatch
records rather than being silently learned from conversation.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from .schemas import Sensitivity, utcnow


class MemoryScope(StrEnum):
    USER = "user"
    TEAM = "team"
    SITE = "site"
    ORGANIZATION = "organization"
    INCIDENT = "incident"


class MemoryItem(BaseModel):
    memory_id: UUID = Field(default_factory=uuid4)
    scope: MemoryScope
    scope_id: UUID
    key: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=8000)
    evidence_ids: list[str] = Field(default_factory=list, max_length=64)
    sensitivity: Sensitivity = Sensitivity.ORGANIZATION
    created_at: datetime = Field(default_factory=utcnow)


class MemoryStore(Protocol):
    async def search(
        self,
        *,
        scope: MemoryScope,
        scope_id: UUID,
        query: str,
        limit: int = 8,
    ) -> list[MemoryItem]: ...

    async def put(self, item: MemoryItem) -> None: ...


class NullMemoryStore:
    async def search(
        self,
        *,
        scope: MemoryScope,
        scope_id: UUID,
        query: str,
        limit: int = 8,
    ) -> list[MemoryItem]:
        _ = (scope, scope_id, query, limit)
        return []

    async def put(self, item: MemoryItem) -> None:
        _ = item
        raise RuntimeError("Memory writes are disabled in the isolated Satchy runtime")


class InMemoryMemoryStore:
    def __init__(self) -> None:
        self.items: list[MemoryItem] = []

    async def search(
        self,
        *,
        scope: MemoryScope,
        scope_id: UUID,
        query: str,
        limit: int = 8,
    ) -> list[MemoryItem]:
        terms = {part.casefold() for part in query.split() if part.strip()}
        matches = [
            item
            for item in self.items
            if item.scope == scope and item.scope_id == scope_id
            and (not terms or any(term in item.content.casefold() for term in terms))
        ]
        return matches[-limit:]

    async def put(self, item: MemoryItem) -> None:
        self.items.append(item)
