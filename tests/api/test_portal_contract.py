import httpx
import pytest

from terrasatch.admin.security import generate_session_secret
from terrasatch.config import Settings
from terrasatch.main import create_app


def make_settings() -> Settings:
    return Settings(
        environment="local",
        deployment_name="portal-test",
        api_base_url="http://testserver",
        admin_session_secret=generate_session_secret(),
    )


@pytest.mark.asyncio
async def test_portal_login_is_available_with_browser_session_secret() -> None:
    application = create_app(make_settings())
    transport = httpx.ASGITransport(app=application)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/portal/login")

    assert response.status_code == 200
    assert "ORGANIZATION PORTAL" in response.text
    assert "individual TerraSatch account" in response.text
    assert 'name="csrf_token"' in response.text


@pytest.mark.asyncio
async def test_portal_dashboard_redirects_to_login_without_member_session() -> None:
    application = create_app(make_settings())
    transport = httpx.ASGITransport(app=application)

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
        follow_redirects=False,
    ) as client:
        response = await client.get("/portal")

    assert response.status_code == 303
    assert response.headers["location"] == "/portal/login"


@pytest.mark.asyncio
async def test_portal_fleet_status_requires_member_session() -> None:
    application = create_app(make_settings())
    transport = httpx.ASGITransport(app=application)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/portal/fleet-status")

    assert response.status_code == 401
    assert response.json()["detail"] == "Portal login required"
