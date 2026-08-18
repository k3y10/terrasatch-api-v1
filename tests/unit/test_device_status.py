from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

from terrasatch.admin.device_status import device_health, device_status_payload, fleet_summary


def _device(*, last_seen_at, enabled=True, capabilities=None, inventory=None, remote_config=None):
    return SimpleNamespace(
        id=uuid4(),
        site_id=uuid4(),
        name="Field Node",
        hostname="field-node",
        platform="linux",
        architecture="x86_64",
        agent_version="test",
        last_seen_at=last_seen_at,
        enabled=enabled,
        capabilities=capabilities or [],
        hardware_inventory=inventory or [],
        remote_config=remote_config or {},
    )


def test_device_health_tracks_online_stale_offline_and_never() -> None:
    now = datetime(2026, 8, 17, 20, 0, tzinfo=UTC)

    assert device_health(_device(last_seen_at=now - timedelta(seconds=30)), now=now)[0] == "online"
    assert device_health(_device(last_seen_at=now - timedelta(minutes=5)), now=now)[0] == "stale"
    assert device_health(_device(last_seen_at=now - timedelta(minutes=30)), now=now)[0] == "offline"
    assert device_health(_device(last_seen_at=None), now=now) == ("never", None)
    assert device_health(_device(last_seen_at=now, enabled=False), now=now) == ("disabled", None)


def test_device_payload_prioritizes_radio_hardware_and_reports_capabilities() -> None:
    now = datetime(2026, 8, 17, 20, 0, tzinfo=UTC)
    device = _device(
        last_seen_at=now - timedelta(seconds=20),
        capabilities=["radio:receive", "radio:transmit"],
        inventory=[
            {"provider": "host", "name": "Bluetooth Network Connection"},
            {"provider": "host", "name": "Integrated Webcam"},
            {"provider": "rtl", "name": "NESDR SMArt v5", "capture_ready": True},
        ],
        remote_config={
            "radio": {
                "receive_enabled": True,
                "transmit_enabled": False,
                "ai_channel": {
                    "agent_name": "Satchy",
                    "activation_phrase": "TerraSatch",
                    "reply_route": "dashboard",
                },
            }
        },
    )

    payload = device_status_payload(device, now=now)

    assert payload["health"] == "online"
    assert payload["hardware"] == "NESDR SMArt v5"
    assert payload["primary_hardware"] == "NESDR SMArt v5"
    assert payload["provider"] == "rtl"
    assert payload["hardware_count"] == 3
    assert payload["rx_supported"] is True
    assert payload["tx_supported"] is True
    assert payload["rx_enabled"] is True
    assert payload["tx_enabled"] is False
    assert payload["mode"] == "RX"
    assert payload["ai_channel"]["agent_name"] == "Satchy"
    assert payload["ai_channel"]["activation_phrase"] == "TerraSatch"


def test_device_payload_does_not_present_host_hardware_as_radio() -> None:
    now = datetime(2026, 8, 17, 20, 0, tzinfo=UTC)
    device = _device(
        last_seen_at=now,
        inventory=[
            {"provider": "host", "name": "Integrated Webcam"},
            {"provider": "host", "name": "Bluetooth Adapter"},
        ],
    )

    payload = device_status_payload(device, now=now)

    assert payload["primary_hardware"] == "No radio hardware reported"
    assert payload["provider"] == "none"
    assert payload["hardware_count"] == 2
    assert payload["rx_supported"] is False


def test_fleet_summary_counts_health_sites_and_radio_capabilities() -> None:
    summary = fleet_summary(
        [
            {"health": "online", "site_id": "a", "rx_supported": True, "tx_supported": False},
            {"health": "online", "site_id": "a", "rx_supported": True, "tx_supported": True},
            {"health": "stale", "site_id": "b", "rx_supported": True, "tx_supported": False},
            {"health": "offline", "site_id": "b", "rx_supported": False, "tx_supported": False},
            {"health": "never", "site_id": "c", "rx_supported": False, "tx_supported": False},
        ]
    )

    assert summary == {
        "total": 5,
        "online": 2,
        "stale": 1,
        "offline": 1,
        "never": 1,
        "disabled": 0,
        "sites": 3,
        "rx_capable": 3,
        "tx_capable": 1,
        "attention": 3,
    }
