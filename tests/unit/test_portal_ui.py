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
        billing={},
        billing_manage_allowed=False,
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


def _workspace(email: str = "keaton@terrasatch.com", organization: str = "org-1") -> str:
    return render_portal(
        display_name="Operator <script>",
        email=email,
        role="operator",
        access_options=[(organization, "Field team")],
        selected_organization=organization,
        selected_name="Field team",
        sites=[],
        devices=[],
        summary={},
        billing={
            "managed": True,
            "plan_code": "team",
            "status": "trialing",
            "service_access": "active",
            "trial_ends_at": "2026-10-10",
        },
        billing_manage_allowed=False,
        csrf_token="csrf",
    )


def test_workspace_inbox_is_lazy_and_org_scoped() -> None:
    from html.parser import HTMLParser

    class Frames(HTMLParser):
        frames: list[dict[str, str | None]] = []

        def handle_starttag(self, tag, attrs):
            if tag == "iframe":
                self.frames.append(dict(attrs))

    html = _workspace(organization="org/one&two")
    parser = Frames()
    parser.feed(html)
    assert len(parser.frames) == 1
    assert "src" not in parser.frames[0]
    assert parser.frames[0]["data-src"] == "/portal/email?organization=org%2Fone%26two&embedded=1"
    assert 'aria-label="Workspace sections"' in html
    assert 'id="organization-form"' in html
    assert "setInterval" not in html
    assert "Operator &lt;script&gt;" in html
    assert 'action="/portal/billing"' not in html
    assert "Trial ends 2026-10-10" in html


def test_customer_email_does_not_load_internal_inbox() -> None:
    html = _workspace(email="operator@customer.example")
    assert "<iframe " not in html
    assert "Customer organization email is not enabled" in html
    assert 'id="services-list"' in html
    assert "/api/v1/workspace/organizations/org-1/integrations/catalog" in html
    assert "Your session has expired" in html
    assert "textContent=item.name" in html
