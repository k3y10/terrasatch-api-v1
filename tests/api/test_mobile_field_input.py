"""Workspace-session acceptance coverage for native mobile field observations."""

from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from terrasatch.admin.security import hash_admin_password
from terrasatch.config import Settings
from terrasatch.database.base import Base
from terrasatch.identity.models import (
    Account,
    Membership,
    MembershipRole,
    Organization,
    Site,
    User,
)
from terrasatch.main import create_app


@pytest.mark.asyncio
async def test_mobile_observation_requires_session_csrf_and_writable_role(monkeypatch) -> None:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as database:
        await database.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    monkeypatch.setattr(
        "terrasatch.workspace.routes.create_session_factory",
        lambda settings: factory,
    )

    async def limiter(*args, **kwargs):
        return None

    monkeypatch.setattr(
        "terrasatch.workspace.routes.enforce_public_rate_limit",
        limiter,
    )

    async with factory() as session:
        account = Account(name="Mobile API account")
        session.add(account)
        await session.flush()
        organization = Organization(
            account_id=account.id,
            name="Mobile API org",
            slug=f"mobile-api-{uuid4().hex[:8]}",
        )
        user = User(
            email=f"{uuid4().hex}@example.com",
            display_name="Mobile Operator",
            enabled=True,
            password_hash=hash_admin_password("Strong-mobile-password-2026!"),
            credential_version=1,
        )
        session.add_all([organization, user])
        await session.flush()
        site = Site(
            organization_id=organization.id,
            name="Mobile API site",
            slug=f"mobile-api-site-{uuid4().hex[:8]}",
        )
        session.add(site)
        session.add(
            Membership(
                organization_id=organization.id,
                user_id=user.id,
                role=MembershipRole.OPERATOR,
                enabled=True,
            )
        )
        await session.commit()
        organization_id = organization.id
        user_id = user.id
        site_id = site.id
        email = user.email

    transmission_id = uuid4()
    transcript_id = uuid4()
    event_id = uuid4()

    async def fake_ingest(
        session,
        settings,
        *,
        organization_id,
        user_id,
        payload,
    ):
        assert organization_id == organization_id_expected
        assert user_id == user_id_expected
        assert payload.site_id == site_id
        assert payload.source_kind == "voice_transcript"
        assert payload.latitude == 40.6
        assert payload.longitude == -111.7
        return (
            SimpleNamespace(id=transmission_id),
            SimpleNamespace(id=transcript_id),
            [SimpleNamespace(id=event_id)],
            False,
        )

    organization_id_expected = organization_id
    user_id_expected = user_id
    monkeypatch.setattr(
        "terrasatch.workspace.routes.ingest_mobile_observation",
        fake_ingest,
    )

    app = create_app(
        Settings(
            environment="local",
            admin_session_secret="mobile-field-test-session-secret",
            intelligence_provider="deterministic",
        )
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        session_info = await client.get("/api/v1/workspace/session")
        csrf = session_info.json()["csrf_token"]
        login = await client.post(
            "/api/v1/workspace/login",
            json={
                "email": email,
                "password": "Strong-mobile-password-2026!",
            },
            headers={"X-CSRF-Token": csrf},
        )
        assert login.status_code == 200

        endpoint = (
            f"/api/v1/workspace/organizations/{organization_id}/field/observations"
        )
        payload = {
            "site_id": str(site_id),
            "client_message_id": "mobile-voice-001",
            "text": "Recent cracking near the ridge.",
            "latitude": 40.6,
            "longitude": -111.7,
            "accuracy_m": 6,
            "source_kind": "voice_transcript",
        }

        no_csrf = await client.post(endpoint, json=payload)
        assert no_csrf.status_code == 403

        accepted = await client.post(
            endpoint,
            json=payload,
            headers={"X-CSRF-Token": login.json()["csrf_token"]},
        )
        assert accepted.status_code == 201
        assert accepted.json() == {
            "transmission_id": str(transmission_id),
            "transcript_id": str(transcript_id),
            "event_ids": [str(event_id)],
            "duplicate": False,
        }

    await engine.dispose()
