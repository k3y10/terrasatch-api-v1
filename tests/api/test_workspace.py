"""Authentication and tenant isolation against a real local SQL database."""

from uuid import uuid4

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from terrasatch.admin.security import hash_admin_password
from terrasatch.config import Settings
from terrasatch.database.base import Base
from terrasatch.identity.models import Account, Membership, MembershipRole, Organization, Site, User
from terrasatch.main import create_app


@pytest.mark.asyncio
async def test_workspace_requires_login_csrf_and_current_membership(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(
        "terrasatch.workspace.routes.create_session_factory", lambda settings: factory
    )

    async def limiter(*args, **kwargs):
        pass

    monkeypatch.setattr("terrasatch.workspace.routes.enforce_public_rate_limit", limiter)
    async with factory() as session:
        account = Account(name="Private account")
        session.add(account)
        await session.flush()
        org = Organization(account_id=account.id, name="Private field program", slug="private")
        session.add(org)
        user = User(
            email="test@example.com",
            display_name="Test member",
            enabled=True,
            password_hash=hash_admin_password("Strong-test-password-2026!"),
        )
        session.add(user)
        await session.flush()
        session.add(
            Membership(
                organization_id=org.id, user_id=user.id, role=MembershipRole.OWNER, enabled=True
            )
        )
        site = Site(organization_id=org.id, name="Real test site", slug="real")
        session.add(site)
        await session.commit()
        site_id = site.id
        organization_id, user_id = org.id, user.id
    app = create_app(
        Settings(admin_session_secret="test-only-session-secret", intelligence_provider="ollama")
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        anonymous = await client.get("/api/v1/workspace/session")
        assert anonymous.json()["user"] is None
        denied = await client.get(f"/api/v1/workspace/organizations/{organization_id}")
        assert denied.status_code == 401
        payload = {"email": "test@example.com", "password": "Strong-test-password-2026!"}
        assert (await client.post("/api/v1/workspace/login", json=payload)).status_code == 403
        login = await client.post(
            "/api/v1/workspace/login",
            json=payload,
            headers={"X-CSRF-Token": anonymous.json()["csrf_token"]},
        )
        assert login.status_code == 200
        own = await client.get(f"/api/v1/workspace/organizations/{organization_id}")
        assert own.status_code == 200
        assert own.json()["records"] == [] and own.json()["messages"] == []
        assert (await client.get(f"/api/v1/workspace/organizations/{uuid4()}")).status_code == 404
        assert (
            await client.post(
                f"/api/v1/workspace/organizations/{organization_id}/chat", json={"message": "hello"}
            )
        ).status_code == 403
        headers = {"X-CSRF-Token": login.json()["csrf_token"]}
        assert own.json()["modules"] == ["Map", "Radio Log", "Observations", "Satchy"]
        assert own.json()["integrations"]["devices"] == []
        prefs_url = f"/api/v1/workspace/organizations/{organization_id}/preferences"
        assert (await client.post(prefs_url, json={"modules": []})).status_code == 403
        assert (
            await client.post(prefs_url, json={"modules": ["unknown-plugin"]}, headers=headers)
        ).status_code == 422
        assert (
            await client.post(
                f"/api/v1/workspace/organizations/{uuid4()}/preferences",
                json={"modules": []},
                headers=headers,
            )
        ).status_code == 404
        changed = await client.post(
            prefs_url, json={"modules": ["Map", "Workflows", "Map"]}, headers=headers
        )
        assert changed.json()["modules"] == ["Map", "Workflows"]
        assert (await client.get(f"/api/v1/workspace/organizations/{organization_id}")).json()[
            "modules"
        ] == ["Map", "Workflows"]
        note = {
            "site_id": str(site_id),
            "request_id": str(uuid4()),
            "text": "Actual test field observation",
            "latitude": 40.7,
            "longitude": -111.5,
        }
        saved = await client.post(
            f"/api/v1/workspace/organizations/{organization_id}/observations",
            json=note,
            headers=headers,
        )
        assert saved.status_code == 200
        again = await client.post(
            f"/api/v1/workspace/organizations/{organization_id}/observations",
            json=note,
            headers=headers,
        )
        assert saved.json() == again.json()
        stored = (await client.get(f"/api/v1/workspace/organizations/{organization_id}")).json()
        assert len(stored["records"]) == 1
        assert stored["records"][0]["original"] == note["text"]
        assert stored["records"][0]["location"]["latitude"] == 40.7
        assert stored["records"][0]["interpretations"] == []
        await client.post(prefs_url, json={"modules": []}, headers=headers)
        hidden = (await client.get(f"/api/v1/workspace/organizations/{organization_id}")).json()
        assert hidden["modules"] == []
        assert hidden["records"][0]["original"] == note["text"]
        foreign_note = {**note, "request_id": str(uuid4()), "site_id": str(uuid4())}
        assert (
            await client.post(
                f"/api/v1/workspace/organizations/{organization_id}/observations",
                json=foreign_note,
                headers=headers,
            )
        ).status_code == 404
        async with factory() as session:
            user = await session.get(User, user_id)
            user.enabled = False
            await session.commit()
        assert (
            await client.get(f"/api/v1/workspace/organizations/{organization_id}")
        ).status_code == 401
    await engine.dispose()
