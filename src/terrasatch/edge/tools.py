"""Read-only local dependency discovery for edge receiver workflows."""

from __future__ import annotations

import shutil
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EdgeToolStatus:
    name: str
    path: str | None
    required_for: str

    @property
    def available(self) -> bool:
        return self.path is not None


def inspect_edge_tools() -> list[EdgeToolStatus]:
    """Report receive-side executables on PATH without running them."""

    definitions = (
        ("rtl_test", "RTL-SDR / Nooelec diagnostics"),
        ("rtl_fm", "RTL-SDR / Nooelec receive audio"),
    )
    return [
        EdgeToolStatus(name=name, path=shutil.which(name), required_for=purpose)
        for name, purpose in definitions
    ]
