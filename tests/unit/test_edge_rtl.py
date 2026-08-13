import shutil
import wave
from array import array

import pytest

from terrasatch.edge.audio import inspect_wav
from terrasatch.edge.rtl import RtlCaptureConfig, build_rtl_fm_command
from terrasatch.edge.tools import inspect_edge_tools


def test_rtl_fm_command_is_receive_only_argument_vector() -> None:
    command = build_rtl_fm_command(
        RtlCaptureConfig(
            frequency_hz=462_575_000,
            duration_seconds=5,
            device="0",
            gain_db=28.0,
            squelch=18,
        )
    )

    assert command[0] == "rtl_fm"
    assert command[command.index("-f") + 1] == "462575000"
    assert command[command.index("-M") + 1] == "fm"
    assert command[command.index("-d") + 1] == "0"
    assert "rtl_tx" not in command
    assert "ptt" not in " ".join(command).lower()


@pytest.mark.parametrize(
    "config",
    [
        RtlCaptureConfig(frequency_hz=0),
        RtlCaptureConfig(frequency_hz=462_575_000, duration_seconds=0.1),
        RtlCaptureConfig(frequency_hz=462_575_000, modulation="invalid"),
    ],
)
def test_rtl_capture_config_rejects_invalid_values(config: RtlCaptureConfig) -> None:
    with pytest.raises(ValueError):
        config.validate()


def test_wav_inspection_reports_pcm_energy(tmp_path) -> None:
    path = tmp_path / "capture.wav"
    samples = array("h", [0, 1000, -1000, 2000, -2000] * 100)
    with wave.open(str(path), "wb") as recording:
        recording.setnchannels(1)
        recording.setsampwidth(2)
        recording.setframerate(16_000)
        recording.writeframes(samples.tobytes())

    report = inspect_wav(path)

    assert report.sample_rate_hz == 16_000
    assert report.channels == 1
    assert report.sample_width_bytes == 2
    assert report.peak == 2000
    assert report.rms is not None and report.rms > 0
    assert report.has_audio_energy is True


def test_edge_tool_discovery_does_not_launch_commands(monkeypatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}" if name == "rtl_test" else None)

    status = {item.name: item for item in inspect_edge_tools()}

    assert status["rtl_test"].available is True
    assert status["rtl_fm"].available is False
