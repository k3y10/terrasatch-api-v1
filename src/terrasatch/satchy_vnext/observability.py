"""Observability contracts for isolated Satchy runs."""

from __future__ import annotations

import asyncio
from pathlib import Path
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



class JsonlTraceStore:
    """Append-only local audit store for sandbox and offline evaluation."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def _append(self, run: AgentRun) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(run.model_dump_json())
            handle.write("\n")

    def _read(self, run_id: UUID) -> AgentRun | None:
        if not self.path.exists():
            return None
        matched: AgentRun | None = None
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                candidate = AgentRun.model_validate_json(line)
                if candidate.run_id == run_id:
                    matched = candidate
        return matched

    async def save(self, run: AgentRun) -> None:
        await asyncio.to_thread(self._append, run)

    async def get(self, run_id: UUID) -> AgentRun | None:
        return await asyncio.to_thread(self._read, run_id)
