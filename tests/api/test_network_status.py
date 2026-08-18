import httpx
import pytest

import terrasatch.main as main_module
from terrasatch.config import Settings
from terrasatch.network.status import capacity_state


def make_settings() -> Settings:
    return Settings(
        environment="local",
        deployment_name="network-status-test",
        api_base_url="http://testserver",
        cors_origins=[],
        max_edge_devices=100,
        max_portal_users=250,
    )


def test_capacity_state_thresholds_and_default_limits() -> None:
    settings = make_settings()
    assert settings.max_edge_devices == 100
    assert settings.max_portal_users == 250
    assert capacity_state(0) == "healthy"
    assert capacity_state(79) == "healthy"
    assert capacity_state(80) == "capacity_watch"
    assert capacity_state(89) == "capacity_watch"
    assert capacity_state(90) == "near_capacity"
    assert capacity_state(99) == "near_capacity"
    assert capacity_state(100) == "registration_paused"


@pytest.mark.asyncio
async def test_public_network_status_requires_no_login_and_exposes_only_aggregates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_status(_settings: Settings) -> dict[str, object]:
        return {
            "generated_at": "2026-08-18T00:00:00Z",
            "registered_nodes": 3,
            "online_nodes": 2,
            "field_sites": 1,
            "members": 4,
            "limits": {"nodes": 100, "members": 250},
            "utilization": {
                "nodes_percent": 3,
                "members_percent": 2,
                "capacity_percent": 3,
            },
            "capacity_state": "healthy",
            "node_registration_open": True,
            "member_registration_open": True,
        }

    monkeypatch.setattr(main_module, "get_public_network_status", fake_status)
    application = main_module.create_app(make_settings())
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/v1/network/status")

    assert response.status_code == 200
    assert "public" in response.headers["cache-control"]
    assert "max-age=15" in response.headers["cache-control"]
    payload = response.json()
    assert payload["registered_nodes"] == 3
    assert payload["online_nodes"] == 2
    assert payload["field_sites"] == 1
    assert payload["members"] == 4
    assert payload["limits"] == {"nodes": 100, "members": 250}
    assert "organization_name" not in payload
    assert "device_id" not in payload
    assert "hardware_inventory" not in payload


@pytest.mark.asyncio
async def test_openapi_exposes_public_network_status() -> None:
    application = main_module.create_app(make_settings())
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/openapi.json")

    assert response.status_code == 200
    assert "get" in response.json()["paths"]["/api/v1/network/status"]
