"""Non-secret local profile for TerraListen edge receivers."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

_ALLOWED_MODES = frozenset({"demo", "organization"})
_ALLOWED_BACKENDS = frozenset({"auto", "rtl", "hackrf"})
_DEFAULT_API_BASE_URL = "https://api.terrasatch.com"


@dataclass(frozen=True, slots=True)
class EdgeProfile:
    mode: str = "demo"
    api_base_url: str = _DEFAULT_API_BASE_URL
    site_id: UUID | None = None
    backend: str = "auto"
    device_id: str | None = None

    def validate(self) -> None:
        if self.mode not in _ALLOWED_MODES:
            raise ValueError("mode must be demo or organization")
        if self.backend not in _ALLOWED_BACKENDS:
            raise ValueError("backend must be auto, rtl, or hackrf")
        if not self.api_base_url.strip():
            raise ValueError("api_base_url cannot be blank")
        if self.mode == "organization" and self.site_id is None:
            raise ValueError("organization mode requires a site_id")

    def to_dict(self) -> dict[str, object]:
        self.validate()
        return {
            "mode": self.mode,
            "api_base_url": self.api_base_url.rstrip("/"),
            "site_id": str(self.site_id) if self.site_id else None,
            "backend": self.backend,
            "device_id": self.device_id,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> EdgeProfile:
        raw_site = payload.get("site_id")
        raw_device = payload.get("device_id")
        profile = cls(
            mode=str(payload.get("mode") or "demo"),
            api_base_url=str(
                payload.get("api_base_url") or _DEFAULT_API_BASE_URL
            ),
            site_id=UUID(str(raw_site)) if raw_site else None,
            backend=str(payload.get("backend") or "auto"),
            device_id=str(raw_device) if raw_device else None,
        )
        profile.validate()
        return profile


def edge_profile_path() -> Path:
    override = os.getenv("TERRASATCH_EDGE_PROFILE", "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".config" / "terrasatch" / "edge.json"


def load_edge_profile(path: str | Path | None = None) -> EdgeProfile:
    resolved = Path(path).expanduser() if path else edge_profile_path()
    if not resolved.exists():
        return EdgeProfile()
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("edge profile must contain a JSON object")
    return EdgeProfile.from_dict(payload)


def save_edge_profile(profile: EdgeProfile, path: str | Path | None = None) -> Path:
    profile.validate()
    resolved = Path(path).expanduser() if path else edge_profile_path()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    try:
        resolved.parent.chmod(0o700)
    except OSError:
        pass
    temporary = resolved.with_suffix(".tmp")
    content = json.dumps(profile.to_dict(), indent=2, sort_keys=True) + "\n"
    temporary.write_text(content, encoding="utf-8")
    try:
        temporary.chmod(0o600)
    except OSError:
        pass
    temporary.replace(resolved)
    try:
        resolved.chmod(0o600)
    except OSError:
        pass
    return resolved
