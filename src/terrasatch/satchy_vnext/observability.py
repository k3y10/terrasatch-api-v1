"""Observability contracts for isolated Satchy runs."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from .schemas import AgentRun


class TraceStore(Protocol):
    async def save(self, run: AgentRun) -> None: ...
    async def get(self, run_id: UUID) -> AgentRun | None: ...


class InMemoryTraceStore:
    def __init__(self) -> None:
        self.runs: dict[UUID, AgentRun] = {}

    async def save(self, run: AgentRun) -> None:
        self.runs[run.run_id] = run.model_copy(deep=True)

    async def get(self, run_id: UUID) -> AgentRun | None:
        run = self.runs.get(run_id)
        return run.model_copy(deep=True) if run is not None else None
