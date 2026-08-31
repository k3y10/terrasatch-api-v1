import httpx
import pytest

from terrasatch.config import Settings
from terrasatch.main import create_app


def make_settings() -> Settings:
    return Settings(
        environment="local",
        deployment_name="edge-contract-test",
        api_base_url="http://testserver",
        cors_origins=[],
    )


@pytest.mark.asyncio
async def test_openapi_exposes_edge_control_plane_routes() -> None:
    application = create_app(make_settings())
    transport = httpx.ASGITransport(app=application)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "post" in paths["/api/v1/edge/pairings"]
    assert "post" in paths["/api/v1/edge/pairings/token"]
    assert "post" in paths["/api/v1/edge/pairings/{user_code}/approve"]
    assert "get" in paths["/api/v1/edge/devices"]
    assert "patch" in paths["/api/v1/edge/devices/{device_id}"]
    assert "get" in paths["/api/v1/edge/me"]
    assert "post" in paths["/api/v1/edge/heartbeat"]
    assert "get" in paths["/api/v1/edge/config"]
    assert "get" in paths["/api/v1/edge/commands"]
    assert "post" in paths["/api/v1/edge/commands/{command_id}/ack"]
    assert "post" in paths["/api/v1/edge/commands/{command_id}/result"]


@pytest.mark.asyncio
async def test_edge_management_requires_bearer_credentials() -> None:
    application = create_app(make_settings())
    transport = httpx.ASGITransport(app=application)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/v1/edge/devices")

    assert response.status_code == 401
    assert response.json()["detail"] == "Bearer token required"


@pytest.mark.asyncio
async def test_public_reference_lists_edge_control_plane() -> None:
    application = create_app(make_settings())
    transport = httpx.ASGITransport(app=application)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/v1/reference")

    assert response.status_code == 200
    payload = response.json()
    catalog = {(item["method"], item["path"]) for item in payload["endpoints"]}
    assert ("POST", "/api/v1/edge/pairings") in catalog
    assert ("POST", "/api/v1/edge/heartbeat") in catalog
    assert ("GET", "/api/v1/edge/config") in catalog
    assert ("GET", "/api/v1/edge/commands") in catalog
    assert ("POST", "/api/v1/edge/commands/{command_id}/ack") in catalog
    assert ("POST", "/api/v1/edge/commands/{command_id}/result") in catalog
    assert "edge:connect" in payload["supported_scopes"]
    assert "read:edge" in payload["supported_scopes"]
    assert "write:edge" in payload["supported_scopes"]
