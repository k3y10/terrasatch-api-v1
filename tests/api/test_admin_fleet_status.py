import httpx
import pytest

from terrasatch.admin.security import generate_session_secret, hash_admin_password
from terrasatch.config import Settings
from terrasatch.main import create_app


@pytest.mark.asyncio
async def test_admin_fleet_status_requires_authenticated_admin_session() -> None:
    application = create_app(
        Settings(
            environment="local",
            deployment_name="test",
            api_base_url="http://testserver",
            admin_email="admin@example.com",
            admin_password_hash=hash_admin_password("a-secure-admin-password"),
            admin_session_secret=generate_session_secret(),
        )
    )
    transport = httpx.ASGITransport(app=application)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/admin/fleet-status")

    assert response.status_code == 401
    assert response.json()["detail"] == "Admin login required"
