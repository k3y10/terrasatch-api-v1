"""Native feedback API contract and founding-team access tests."""

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from terrasatch.admin.security import hash_admin_password
from terrasatch.config import Settings
from terrasatch.database.base import Base
from terrasatch.feedback.models import SurveyResponse
from terrasatch.identity.models import Account, Membership, MembershipRole, Organization, User
from terrasatch.main import create_app


@pytest.mark.asyncio
async def test_native_feedback_is_anonymous_and_founder_only(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr("terrasatch.feedback.routes.create_session_factory", lambda settings: factory)

    async def limiter(*args, **kwargs):
        return None

    monkeypatch.setattr("terrasatch.feedback.routes.enforce_public_rate_limit", limiter)

    async with factory() as session:
        account = Account(name="TerraSatch internal")
        session.add(account)
        await session.flush()
        org = Organization(account_id=account.id, name="Founding team", slug="founding-team")
        founder = User(
            email="founder@example.test",
            display_name="Founder",
            enabled=True,
            password_hash=hash_admin_password("Strong-test-password-2026!"),
            credential_version=1,
        )
        other_owner = User(
            email="customer-owner@example.test",
            display_name="Customer owner",
            enabled=True,
            password_hash=hash_admin_password("Strong-test-password-2026!"),
            credential_version=1,
        )
        session.add_all([org, founder, other_owner])
        await session.flush()
        session.add_all(
            [
                Membership(
                    organization_id=org.id,
                    user_id=founder.id,
                    role=MembershipRole.OWNER,
                    enabled=True,
                ),
                Membership(
                    organization_id=org.id,
                    user_id=other_owner.id,
                    role=MembershipRole.OWNER,
                    enabled=True,
                ),
            ]
        )
        await session.commit()
        org_id = org.id

    app = create_app(
        Settings(
            environment="local",
            admin_session_secret="test-only-session-secret",
            feedback_internal_emails=["founder@example.test"],
        )
    )

    payload = {
        "source_code": "brighton-01",
        "audience": "recreation",
        "primary_tool": "phone_apps",
        "primary_hassle": "losing_service",
        "connectivity": "often",
        "spend_band": "100_249",
        "concept_interest": "would_try",
        "comment": "Make offline handoff easier.",
    }

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        saved = await client.post("/api/v1/feedback/responses", json=payload)
        assert saved.status_code == 201
        assert saved.json()["accepted"] is True

        async with factory() as session:
            rows = list(await session.scalars(select(SurveyResponse)))
            assert len(rows) == 1
            assert rows[0].source_code == "brighton-01"
            assert "email" not in rows[0].answers
            assert rows[0].audience == "recreation"

        assert (await client.get("/api/v1/feedback/giveaways/ski-day-2026-27")).status_code == 404

        anonymous = await client.get("/api/v1/workspace/session")
        login = await client.post(
            "/api/v1/workspace/login",
            json={"email": "founder@example.test", "password": "Strong-test-password-2026!"},
            headers={"X-CSRF-Token": anonymous.json()["csrf_token"]},
        )
        assert login.status_code == 200

        summary = await client.get(f"/api/v1/workspace/organizations/{org_id}/feedback/summary")
        assert summary.status_code == 200
        assert summary.json()["responses"] == 1
        assert summary.json()["source"] == {"brighton-01": 1}
        assert "campaign" not in summary.json()

        export = await client.get(f"/api/v1/workspace/organizations/{org_id}/feedback/export.csv")
        assert export.status_code == 200
        assert "brighton-01" in export.text
        assert "email" not in export.text.splitlines()[0].casefold()

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        anonymous = await client.get("/api/v1/workspace/session")
        login = await client.post(
            "/api/v1/workspace/login",
            json={"email": "customer-owner@example.test", "password": "Strong-test-password-2026!"},
            headers={"X-CSRF-Token": anonymous.json()["csrf_token"]},
        )
        assert login.status_code == 200
        denied = await client.get(f"/api/v1/workspace/organizations/{org_id}/feedback/summary")
        assert denied.status_code == 403

    await engine.dispose()
