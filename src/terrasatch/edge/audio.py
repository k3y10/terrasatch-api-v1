"""Small dependency-free audio helpers used by receive-side edge diagnostics."""

from __future__ import annotations

import wave
from pathlib import Path


def inspect_wav(path: Path) -> dict[str, object]:
    """Return bounded WAV metadata without loading the full file into memory."""

    resolved = path.expanduser().resolve()
    with wave.open(str(resolved), "rb") as wav:
        frames = wav.getnframes()
        sample_rate = wav.getframerate()
        duration = frames / sample_rate if sample_rate else 0.0
        return {
            "path": str(resolved),
            "channels": wav.getnchannels(),
            "sample_width_bytes": wav.getsampwidth(),
            "sample_rate": sample_rate,
            "frames": frames,
            "duration_seconds": round(duration, 3),
        }
