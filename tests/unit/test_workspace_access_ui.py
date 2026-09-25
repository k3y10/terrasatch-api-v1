import pytest

from terrasatch.portal.access_ui import render_workspace_access


@pytest.mark.parametrize(
    ("billing", "expected"),
    [
        ({}, "Confirm organization access"),
        ({"managed": True, "service_access": "full", "entitlements": {"api_access": False}},
         "Not included in your plan"),
        ({"managed": True, "service_access": "full", "entitlements": {"api_access": True}},
         "Included in your plan"),
        ({"managed": True, "service_access": "restricted", "entitlements": {"api_access": True}},
         "Restricted by billing"),
        ({"managed": True, "service_access": "unknown", "entitlements": {"api_access": True}},
         "Restricted by billing"),
    ],
)
def test_access_panel_does_not_grant_access_from_plan_alone(billing, expected):
    html = render_workspace_access(
        billing, device_count=0, site_count=1, online_count=0, can_manage=False,
    )
    assert expected in html
    assert "Administrator required" in html
    assert "In development" in html
    assert "BETA WORKSPACE" in html


def test_limits_are_not_reported_as_remaining_usage_and_are_escaped():
    html = render_workspace_access(
        {"managed": True, "service_access": "grace", "entitlements": {
            "max_edge_devices": 6, "max_sites": "<script>bad</script>",
            "included_processing_hours": 75,
        }}, device_count=2, site_count=1, online_count=1, can_manage=True,
    )
    assert "2 registered · limit 6" in html
    assert "Included allowance: 75" in html
    assert "not remaining usage" in html
    assert "Temporary grace access may end" in html
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "Admin access" in html
