import wave
from pathlib import Path

from terrasatch.edge.audio import inspect_wav


def test_inspect_wav_reports_capture_metadata(tmp_path: Path) -> None:
    path = tmp_path / "radio.wav"
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(24_000)
        wav.writeframes(b"\x00\x00" * 24_000)

    result = inspect_wav(path)

    assert result["channels"] == 1
    assert result["sample_width_bytes"] == 2
    assert result["sample_rate"] == 24_000
    assert result["frames"] == 24_000
    assert result["duration_seconds"] == 1.0
