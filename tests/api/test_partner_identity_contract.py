import httpx
import pytest

from terrasatch.admin.security import generate_session_secret
from terrasatch.config import Settings
from terrasatch.main import create_app


def make_settings() -> Settings:
    return Settings(
        environment="local",
        deployment_name="partner-identity-contract-test",
        api_base_url="http://testserver",
        admin_session_secret=generate_session_secret(),
        cors_origins=[],
    )


@pytest.mark.asyncio
async def test_openapi_exposes_team_membership_and_scoped_integration_routes() -> None:
    application = create_app(make_settings())
    transport = httpx.ASGITransport(app=application)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert {"get", "put"}.issubset(paths["/api/v1/team-memberships/{user_id}"])
    assert "get" in paths["/api/v1/integrations/flaik/status"]
    assert "post" in paths["/api/v1/integrations/flaik/correlate"]


@pytest.mark.asyncio
async def test_public_reference_lists_partner_identity_and_integration_contracts() -> None:
    application = create_app(make_settings())
    transport = httpx.ASGITransport(app=application)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/v1/reference")

    assert response.status_code == 200
    catalog = {(item["method"], item["path"]) for item in response.json()["endpoints"]}
    assert ("GET", "/api/v1/team-memberships/{user_id}") in catalog
    assert ("PUT", "/api/v1/team-memberships/{user_id}") in catalog
    assert ("GET", "/api/v1/integrations/flaik/status") in catalog
    assert ("POST", "/api/v1/integrations/flaik/correlate") in catalog


@pytest.mark.asyncio
async def test_partner_integration_requires_tenant_service_credential() -> None:
    application = create_app(make_settings())
    transport = httpx.ASGITransport(app=application)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/v1/integrations/flaik/status")

    assert response.status_code == 401
    assert response.json()["detail"] == "Bearer token required"


@pytest.mark.asyncio
async def test_portal_context_requires_human_session() -> None:
    application = create_app(make_settings())
    transport = httpx.ASGITransport(app=application)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/portal/context")

    assert response.status_code == 401
    assert response.json()["detail"] == "Portal login required"
