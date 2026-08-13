import httpx
import pytest

from terrasatch.config import Settings
from terrasatch.main import create_app


def make_settings() -> Settings:
    return Settings(
        environment="local",
        deployment_name="control-plane-contract-test",
        api_base_url="http://testserver",
        cors_origins=[],
    )


@pytest.mark.asyncio
async def test_openapi_exposes_site_and_team_lifecycle_routes() -> None:
    application = create_app(make_settings())
    transport = httpx.ASGITransport(app=application)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert {"get", "post"}.issubset(paths["/api/v1/sites"])
    assert {"get", "patch"}.issubset(paths["/api/v1/sites/{site_id}"])
    assert {"get", "post"}.issubset(paths["/api/v1/teams"])
    assert {"get", "patch"}.issubset(paths["/api/v1/teams/{team_id}"])


@pytest.mark.asyncio
async def test_control_plane_resources_require_bearer_credentials() -> None:
    application = create_app(make_settings())
    transport = httpx.ASGITransport(app=application)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/v1/teams")

    assert response.status_code == 401
    assert response.json()["detail"] == "Bearer token required"


@pytest.mark.asyncio
async def test_public_reference_lists_site_and_team_lifecycle() -> None:
    application = create_app(make_settings())
    transport = httpx.ASGITransport(app=application)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/v1/reference")

    catalog = {(item["method"], item["path"]) for item in response.json()["endpoints"]}
    assert ("PATCH", "/api/v1/sites/{site_id}") in catalog
    assert ("POST", "/api/v1/teams") in catalog
    assert ("GET", "/api/v1/teams/{team_id}") in catalog
    assert ("PATCH", "/api/v1/teams/{team_id}") in catalog
