from pathlib import Path

import pytest

from terrasatch.edge import rtl
from terrasatch.edge.rtl import RTLReceiveConfig, build_rtl_fm_command


def test_rtl_receive_config_rejects_invalid_values() -> None:
    with pytest.raises(ValueError):
        RTLReceiveConfig(frequency_hz=0)
    with pytest.raises(ValueError):
        RTLReceiveConfig(frequency_hz=155_000_000, squelch=101)
    with pytest.raises(ValueError):
        RTLReceiveConfig(frequency_hz=155_000_000, modulation="digital")


def test_build_rtl_fm_command_is_receive_only_argv(monkeypatch) -> None:
    monkeypatch.setattr(rtl.shutil, "which", lambda name: f"/usr/bin/{name}")
    config = RTLReceiveConfig(
        frequency_hz=155_000_000,
        sample_rate=24_000,
        output_rate=24_000,
        device="1",
        gain_db=28.0,
        squelch=12,
    )

    command = build_rtl_fm_command(config)

    assert command[0] == "/usr/bin/rtl_fm"
    assert command[command.index("-f") + 1] == "155000000"
    assert command[command.index("-M") + 1] == "fm"
    assert command[command.index("-d") + 1] == "1"
    assert command[command.index("-g") + 1] == "28"
    assert command[command.index("-l") + 1] == "12"
    assert command[-1] == "-"
    assert not any("ptt" in item.casefold() or "transmit" in item.casefold() for item in command)


def test_find_rtl_tools_reports_missing_tools(monkeypatch) -> None:
    monkeypatch.setattr(rtl.shutil, "which", lambda _name: None)

    assert rtl.find_rtl_tools() == {"rtl_test": None, "rtl_fm": None}


def test_capture_requires_bounded_duration(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(rtl.shutil, "which", lambda name: f"/usr/bin/{name}")
    config = RTLReceiveConfig(frequency_hz=155_000_000)

    with pytest.raises(ValueError):
        rtl.capture_rtl_wav(config, seconds=0, output_path=tmp_path / "capture.wav")
