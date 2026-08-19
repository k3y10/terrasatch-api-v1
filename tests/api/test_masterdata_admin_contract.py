import httpx
import pytest

from terrasatch.admin.security import hash_admin_password
from terrasatch.config import Settings
from terrasatch.main import create_app


def make_settings() -> Settings:
    return Settings(
        environment="local",
        deployment_name="masterdata-admin-contract-test",
        api_base_url="http://testserver",
        cors_origins=[],
    )


@pytest.mark.asyncio
async def test_app_registers_control_plane_data_routes_outside_openapi() -> None:
    settings = Settings(
        environment="local",
        deployment_name="masterdata-admin-contract-test",
        api_base_url="http://testserver",
        cors_origins=[],
        admin_email="admin@example.com",
        admin_password_hash=hash_admin_password("test-password"),
        admin_session_secret="test-session-secret-with-sufficient-length",
    )
    application = create_app(settings)
    transport = httpx.ASGITransport(app=application)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        sources = await client.get("/admin/data-sources")
        inspector = await client.get("/admin/data-inspector")

    assert sources.status_code == 401
    assert inspector.status_code == 401
    assert "/admin/data-sources" not in application.openapi()["paths"]


@pytest.mark.asyncio
async def test_data_pages_are_unavailable_when_admin_is_not_configured() -> None:
    application = create_app(make_settings())
    transport = httpx.ASGITransport(app=application)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/admin/data-sources")

    assert response.status_code == 404
