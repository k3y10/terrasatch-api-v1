from terrasatch.portal.ui import render_portal, render_portal_edge_device


def test_portal_renders_membership_role_and_multiple_edge_devices() -> None:
    html = render_portal(
        display_name="Field Operator",
        email="operator@example.com",
        role="operator",
        access_options=[("org-1", "UAC")],
        selected_organization="org-1",
        selected_name="UAC",
        sites=[object(), object()],
        devices=[
            {
                "id": "edge-1",
                "health": "online",
                "agent_version": "0.2.8",
                "platform": "Windows",
                "architecture": "x86_64",
                "age_seconds": 20,
                "name": "Wasatch Edge",
                "hostname": "wasatch-edge",
                "primary_hardware": "NESDR SMArt v5",
                "provider": "rtl",
                "rx_supported": True,
                "rx_enabled": True,
                "tx_supported": False,
                "tx_enabled": False,
                "mode": "RX",
            },
            {
                "id": "edge-2",
                "health": "stale",
                "agent_version": "0.2.7",
                "platform": "Linux",
                "architecture": "x86_64",
                "age_seconds": 300,
                "name": "Gateway Edge",
                "hostname": "gateway-edge",
                "primary_hardware": "Field Radio Gateway",
                "provider": "gateway",
                "rx_supported": True,
                "rx_enabled": True,
                "tx_supported": True,
                "tx_enabled": False,
                "mode": "RX",
            },
        ],
        summary={
            "online": 1,
            "total": 2,
            "sites": 2,
            "rx_capable": 2,
            "tx_capable": 1,
            "attention": 1,
        },
        csrf_token="csrf",
        billing={},
        billing_manage_allowed=False,
        edge_troubleshoot_allowed=True,
        edge_manage_allowed=False,
    )
    assert "/assets/satchy.png" in html

    assert "ROLE · OPERATOR" in html
    assert "Wasatch Edge" in html
    assert "NESDR SMArt v5" in html
    assert "Gateway Edge" in html
    assert "Field Radio Gateway" in html
    assert "RX ON" in html
    assert "TX READY" in html
    assert "1 / 2" in html


def test_operator_portal_renders_edge_inspect_without_admin_controls() -> None:
    html = render_portal_edge_device(
        display_name="Patrol Supervisor",
        role="operator",
        organization_id="org-1",
        organization_name="UAC",
        device={
            "id": "edge-1",
            "site_id": "site-1",
            "name": "Wasatch Edge",
            "hostname": "wasatch-edge",
            "platform": "Windows",
            "architecture": "AMD64",
            "agent_version": "0.2.8",
            "enabled": True,
            "health": "online",
            "last_seen_at": "2026-09-22T16:30:00+00:00",
            "primary_hardware": "NESDR SMArt v5",
            "provider": "rtl",
            "mode": "RX",
            "rx_enabled": True,
            "rx_supported": True,
            "tx_enabled": False,
            "tx_supported": False,
            "capabilities": ["audio:capture", "radio:receive"],
            "hardware_inventory": [{"provider": "rtl", "name": "NESDR SMArt v5"}],
            "telemetry": {"radio": {"state": "listening"}},
            "remote_config": {"radio": {"receive_enabled": True}},
            "ai_channel": {"agent_name": "Satchy", "reply_route": "dashboard"},
        },
        sites=[],
        manage_allowed=False,
        csrf_token="csrf",
    )

    assert "EDGE DIAGNOSTICS" in html
    assert "0.2.8" in html
    assert "Latest heartbeat telemetry" in html
    assert "Operator troubleshooting" in html
    assert "Save device settings" not in html
    assert "listening" in html
    assert "receive_enabled" in html


def test_admin_portal_renders_bounded_edge_management_controls() -> None:
    class Site:
        id = "site-1"
        name = "Big Cottonwood"

    html = render_portal_edge_device(
        display_name="Operations Manager",
        role="admin",
        organization_id="org-1",
        organization_name="UAC",
        device={
            "id": "edge-1",
            "site_id": "site-1",
            "name": "Wasatch Edge",
            "enabled": True,
            "health": "online",
        },
        sites=[Site()],
        manage_allowed=True,
        csrf_token="csrf",
    )

    assert "Device management" in html
    assert "Save device settings" in html
    assert "Big Cottonwood" in html
    assert "This does not enable RF transmit" in html
