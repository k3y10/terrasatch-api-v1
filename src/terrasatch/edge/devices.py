"""Receiver registry for TerraListen edge hardware."""

from __future__ import annotations

import shutil
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReceiverDevice:
    backend: str
    name: str
    device_id: str | None
    capture_ready: bool
    detail: str


def discover_receivers() -> list[ReceiverDevice]:
    """Discover installed receive backends without requiring an organization or API key."""

    devices: list[ReceiverDevice] = []
    rtl_test = shutil.which("rtl_test")
    rtl_fm = shutil.which("rtl_fm")
    if rtl_test or rtl_fm:
        devices.append(
            ReceiverDevice(
                backend="rtl",
                name="RTL-SDR / Nooelec",
                device_id=None,
                capture_ready=bool(rtl_test and rtl_fm),
                detail=(
                    "receive audio ready"
                    if rtl_test and rtl_fm
                    else "install both rtl_test and rtl_fm"
                ),
            )
        )

    hackrf_info = shutil.which("hackrf_info")
    if hackrf_info:
        devices.append(
            ReceiverDevice(
                backend="hackrf",
                name="HackRF",
                device_id=None,
                capture_ready=False,
                detail="discovery available; TerraListen audio adapter not enabled yet",
            )
        )
    return devices


def select_receiver(
    devices: list[ReceiverDevice],
    *,
    backend: str = "auto",
) -> ReceiverDevice:
    """Choose a capture-capable receiver, preferring RTL for the current release."""

    if backend not in {"auto", "rtl", "hackrf"}:
        raise ValueError("backend must be auto, rtl, or hackrf")
    candidates = (
        devices if backend == "auto" else [item for item in devices if item.backend == backend]
    )
    for item in candidates:
        if item.capture_ready:
            return item
    if candidates:
        raise RuntimeError(f"{candidates[0].name} is detected but receive audio is not ready")
    raise RuntimeError("No compatible TerraListen receiver backend was detected")
