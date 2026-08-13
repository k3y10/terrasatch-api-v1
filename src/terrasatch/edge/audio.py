"""Dependency-free WAV diagnostics for field receiver captures."""

from __future__ import annotations

import math
import sys
import wave
from array import array
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AudioDiagnostics:
    path: Path
    duration_seconds: float
    sample_rate_hz: int
    channels: int
    sample_width_bytes: int
    frame_count: int
    rms: float | None
    peak: int | None

    @property
    def has_audio_energy(self) -> bool:
        return bool(self.peak and self.peak > 0)


def _pcm_levels(payload: bytes, sample_width: int) -> tuple[float | None, int | None]:
    if not payload:
        return 0.0, 0
    if sample_width == 1:
        samples = [value - 128 for value in payload]
    elif sample_width == 2:
        values = array("h")
        values.frombytes(payload)
        if sys.byteorder != "little":
            values.byteswap()
        samples = values
    else:
        return None, None

    peak = max(abs(value) for value in samples)
    mean_square = sum(value * value for value in samples) / len(samples)
    return math.sqrt(mean_square), peak


def inspect_wav(path: str | Path) -> AudioDiagnostics:
    """Inspect a PCM WAV capture without requiring external audio packages."""

    resolved = Path(path).expanduser().resolve()
    with wave.open(str(resolved), "rb") as recording:
        channels = recording.getnchannels()
        sample_rate = recording.getframerate()
        sample_width = recording.getsampwidth()
        frames = recording.getnframes()
        payload = recording.readframes(frames)

    rms, peak = _pcm_levels(payload, sample_width)
    duration = frames / sample_rate if sample_rate else 0.0
    return AudioDiagnostics(
        path=resolved,
        duration_seconds=duration,
        sample_rate_hz=sample_rate,
        channels=channels,
        sample_width_bytes=sample_width,
        frame_count=frames,
        rms=rms,
        peak=peak,
    )
