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


def test_device_payload_reports_hardware_rx_tx_mode_and_satchy_policy() -> None:
    now = datetime(2026, 8, 17, 20, 0, tzinfo=UTC)
    device = _device(
        last_seen_at=now - timedelta(seconds=20),
        capabilities=["radio:receive", "radio:transmit"],
        inventory=[{"provider": "gateway", "name": "Field Radio Gateway"}],
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
    assert payload["hardware"] == "Field Radio Gateway"
    assert payload["rx_supported"] is True
    assert payload["tx_supported"] is True
    assert payload["rx_enabled"] is True
    assert payload["tx_enabled"] is False
    assert payload["mode"] == "RX"
    assert payload["ai_channel"]["agent_name"] == "Satchy"
    assert payload["ai_channel"]["activation_phrase"] == "TerraSatch"


def test_fleet_summary_counts_health_states() -> None:
    summary = fleet_summary(
        [
            {"health": "online"},
            {"health": "online"},
            {"health": "stale"},
            {"health": "offline"},
            {"health": "never"},
        ]
    )

    assert summary == {
        "total": 5,
        "online": 2,
        "stale": 1,
        "offline": 1,
        "never": 1,
        "disabled": 0,
    }
