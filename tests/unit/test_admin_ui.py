from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from terrasatch.admin.ui import _styles, render_login
from terrasatch.admin.ui_v3 import render_dashboard


def test_admin_ui_uses_orange_terminal_theme() -> None:
    styles = _styles()
    html = render_login("csrf-token", failed=False)

    assert "--accent:#ff8a00" in styles
    assert "#166534" not in styles
    assert "ts-admin@terrasatch" in html
    assert "establish session" in html
    assert "/assets/terralisten-sasquatch.webp" in html


def test_dashboard_exposes_real_admin_commands_satchy_and_live_edge_health() -> None:
    organization_id = uuid4()
    site_id = uuid4()
    device_id = uuid4()
    device = SimpleNamespace(
        id=device_id,
        site_id=site_id,
        name="Field Node",
        hostname="field-node",
        platform="linux",
        architecture="x86_64",
        agent_version="test",
        last_seen_at=datetime.now(UTC),
        capabilities=["radio:receive", "radio:transmit"],
        hardware_inventory=[{"provider": "test-full-duplex", "name": "Test Radio"}],
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
        enabled=True,
    )
    organization = SimpleNamespace(
        id=organization_id,
        name="UAC",
        slug="uac",
        enabled=True,
    )
    site = SimpleNamespace(id=site_id, name="Wasatch", slug="wasatch", enabled=True)

    html = render_dashboard(
        report_status="pass",
        components=[],
        endpoints=[],
        errors=[],
        organizations=[organization],
        selected_organization=str(organization_id),
        selected_name="UAC",
        selected_slug="uac",
        selected_enabled=True,
        sites=[site],
        edge_devices=[device],
        api_keys=[],
        csrf_token="csrf-token",
        error_message=None,
    )

    assert "/admin/command" in html
    assert "edge tx" in html
    assert "TX off" in html
    assert "PROVIDER-AWARE RX / TX" in html
    assert "CAPABILITY-GATED RADIO" in html
    assert "arbitrary OS shell" in html
    assert "Registered device health" in html
    assert "Heartbeat-backed state" in html
    assert "ONLINE" in html
    assert "Test Radio" in html
    assert "RX ON" in html
    assert "TX READY" in html
    assert "/admin/fleet-status" in html
    assert "setInterval(refresh,10000)" in html
    assert "--fleet-green:#6ee7a0" in html
    assert ".status-dot.pass,.status-dot.healthy" in html
    assert ".status-dot.degraded" in html
    assert ".status-dot.unhealthy,.status-dot.error" in html
    assert "Satchy AI Channel" in html
    assert "edge ai" in html
    assert "Logical first, provider bound" in html
    assert "/admin/members" in html
    assert "Members & access" in html
