"""Native feedback API contract, privacy separation, and founding-team access tests."""

from uuid import uuid4

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from terrasatch.admin.security import hash_admin_password
from terrasatch.config import Settings
from terrasatch.database.base import Base
from terrasatch.feedback.models import GiveawayEntry, SurveyResponse
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
                Membership(organization_id=org.id, user_id=founder.id, role=MembershipRole.OWNER, enabled=True),
                Membership(organization_id=org.id, user_id=other_owner.id, role=MembershipRole.OWNER, enabled=True),
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
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        meta = await client.get("/api/v1/feedback/campaigns/outdoor-field-check-in-fall-2026")
        assert meta.status_code == 200
        assert meta.json()["anonymous_by_default"] is True
        assert meta.json()["giveaway"]["active"] is False

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
        saved = await client.post(
            "/api/v1/feedback/campaigns/outdoor-field-check-in-fall-2026/responses",
            json=payload,
        )
        assert saved.status_code == 201

        blocked_giveaway = await client.post(
            "/api/v1/feedback/giveaways/ski-day-2026-27/entries",
            json={
                "name": "Test Person",
                "email": "person@example.test",
                "resort_preference": "either",
                "rules_accepted": True,
            },
        )
        assert blocked_giveaway.status_code == 409

        async with factory() as session:
            rows = list(await session.scalars(__import__("sqlalchemy").select(SurveyResponse)))
            entries = list(await session.scalars(__import__("sqlalchemy").select(GiveawayEntry)))
            assert len(rows) == 1
            assert entries == []
            assert "email" not in rows[0].answers
            assert rows[0].source_code == "brighton-01"

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
        export = await client.get(f"/api/v1/workspace/organizations/{org_id}/feedback/export.csv")
        assert export.status_code == 200
        assert "brighton-01" in export.text
        assert "person@example.test" not in export.text

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
