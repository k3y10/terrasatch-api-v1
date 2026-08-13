"""Local dependency discovery for receive-only edge workflows."""

from __future__ import annotations

import shutil
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EdgeToolStatus:
    """Availability of one optional edge executable."""

    name: str
    path: str | None
    required_for: str

    @property
    def available(self) -> bool:
        return self.path is not None


EDGE_TOOLS: tuple[tuple[str, str], ...] = (
    ("rtl_test", "RTL-SDR device diagnostics"),
    ("rtl_fm", "RTL-SDR receive and FM demodulation"),
)


def inspect_edge_tools() -> list[EdgeToolStatus]:
    """Return tool availability without launching or changing any device."""

    return [
        EdgeToolStatus(name=name, path=shutil.which(name), required_for=required_for)
        for name, required_for in EDGE_TOOLS
    ]
