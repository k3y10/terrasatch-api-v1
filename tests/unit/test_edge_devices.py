import shutil

import pytest

from terrasatch.edge.devices import discover_receivers, select_receiver


def test_discovery_reports_rtl_capture_ready_and_hackrf_discovery_only(monkeypatch) -> None:
    tools = {
        "rtl_test": "/usr/bin/rtl_test",
        "rtl_fm": "/usr/bin/rtl_fm",
        "hackrf_info": "/usr/bin/hackrf_info",
    }
    monkeypatch.setattr(shutil, "which", lambda name: tools.get(name))

    devices = discover_receivers()
    by_backend = {item.backend: item for item in devices}

    assert by_backend["rtl"].capture_ready is True
    assert by_backend["hackrf"].capture_ready is False
    assert "not enabled yet" in by_backend["hackrf"].detail
    assert select_receiver(devices).backend == "rtl"


def test_hackrf_only_does_not_fake_receive_audio_support(monkeypatch) -> None:
    monkeypatch.setattr(
        shutil,
        "which",
        lambda name: "/usr/bin/hackrf_info" if name == "hackrf_info" else None,
    )

    devices = discover_receivers()

    assert len(devices) == 1
    assert devices[0].backend == "hackrf"
    with pytest.raises(RuntimeError, match="detected"):
        select_receiver(devices, backend="hackrf")
