from terrasatch.portal.ui import render_portal


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
                "health": "online",
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
                "health": "stale",
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
