import re
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest

from terrasatch.admin.security import generate_session_secret
from terrasatch.config import Settings
from terrasatch.main import create_app


def csrf_token(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match is not None
    return match.group(1)

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
    assert "FIELD WORKSPACE" in response.text
    assert "Open your TerraSatch workspace" in response.text
    assert 'href="/portal/forgot-password"' in response.text
    assert 'href="/portal/resend-activation"' in response.text
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


@pytest.mark.asyncio
async def test_portal_account_recovery_pages_are_available() -> None:
    application = create_app(make_settings())
    transport = httpx.ASGITransport(app=application)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        forgot = await client.get("/portal/forgot-password")
        resend = await client.get("/portal/resend-activation")
        reset = await client.get("/portal/reset-password")

    assert forgot.status_code == 200
    assert "Reset your password" in forgot.text
    assert resend.status_code == 200
    assert "Resend your setup email" in resend.text
    assert reset.status_code == 200
    assert "Create a new password" in reset.text
    assert 'id="reset-token"' in reset.text


@pytest.mark.asyncio
async def test_superadmin_portal_login_unlocks_admin_session(monkeypatch) -> None:
    user = SimpleNamespace(
        id=uuid4(),
        credential_version=4,
        email="keaton@terrasatch.com",
        display_name="Keaton",
        is_superadmin=True,
    )

    async def fake_authenticate(_session, *, email: str, password: str):
        assert email == user.email
        assert password == "founder-password"
        return user

    async def fake_database(_settings, operation):
        return await operation(None)

    monkeypatch.setattr("terrasatch.portal.routes.authenticate_user", fake_authenticate)
    monkeypatch.setattr("terrasatch.portal.routes._run_database", fake_database)

    application = create_app(make_settings())
    transport = httpx.ASGITransport(app=application)

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
        follow_redirects=False,
    ) as client:
        login = await client.get("/portal/login")
        signed_in = await client.post(
            "/portal/login",
            data={
                "email": user.email,
                "password": "founder-password",
                "csrf_token": csrf_token(login.text),
            },
        )
        assert signed_in.status_code == 303
        admin_login = await client.get("/admin/login")

    assert admin_login.status_code == 303
    assert admin_login.headers["location"] == "/admin"


@pytest.mark.asyncio
async def test_regular_portal_user_does_not_gain_admin_access(monkeypatch) -> None:
    user = SimpleNamespace(
        id=uuid4(),
        credential_version=1,
        email="member@terrasatch.com",
        display_name="Member",
        is_superadmin=False,
    )

    async def fake_authenticate(_session, *, email: str, password: str):
        return user

    async def fake_database(_settings, operation):
        return await operation(None)

    monkeypatch.setattr("terrasatch.portal.routes.authenticate_user", fake_authenticate)
    monkeypatch.setattr("terrasatch.portal.routes._run_database", fake_database)

    application = create_app(make_settings())
    transport = httpx.ASGITransport(app=application)

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
        follow_redirects=False,
    ) as client:
        login = await client.get("/portal/login")
        signed_in = await client.post(
            "/portal/login",
            data={
                "email": user.email,
                "password": "member-password",
                "csrf_token": csrf_token(login.text),
            },
        )
        assert signed_in.status_code == 303
        admin = await client.get("/admin/fleet-status")

    assert admin.status_code == 401


@pytest.mark.asyncio
async def test_superadmin_admin_login_establishes_portal_identity(monkeypatch) -> None:
    user = SimpleNamespace(
        id=uuid4(),
        credential_version=2,
        email="keaton@terrasatch.com",
        display_name="Keaton",
        is_superadmin=True,
    )

    async def fake_authenticate(_session, *, email: str, password: str):
        assert email == user.email
        assert password == "founder-password"
        return user

    async def fake_database(_settings, operation):
        return await operation(None)

    async def fake_require_user(_request, _settings, *, session=None):
        return user.id

    monkeypatch.setattr("terrasatch.admin.routes.authenticate_user", fake_authenticate)
    monkeypatch.setattr("terrasatch.admin.routes._run_database", fake_database)
    monkeypatch.setattr("terrasatch.portal.routes._require_user", fake_require_user)

    application = create_app(make_settings())
    transport = httpx.ASGITransport(app=application)

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
        follow_redirects=False,
    ) as client:
        login = await client.get("/admin/login")
        signed_in = await client.post(
            "/admin/login",
            data={
                "email": user.email,
                "password": "founder-password",
                "csrf_token": csrf_token(login.text),
            },
        )
        assert signed_in.status_code == 303
        portal_login = await client.get("/portal/login")

    assert portal_login.status_code == 303
    assert portal_login.headers["location"] == "/portal"
