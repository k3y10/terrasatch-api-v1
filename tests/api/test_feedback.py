"""Native adaptive feedback, first-party distribution, and founding-team access tests."""

from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from terrasatch.admin.security import hash_admin_password
from terrasatch.config import Settings
from terrasatch.database.base import Base
from terrasatch.feedback.models import FeedbackDistribution, SurveyResponse
from terrasatch.identity.models import (
    Account,
    Membership,
    MembershipRole,
    Organization,
    User,
)
from terrasatch.main import create_app


def recreation_payload(distribution_id: str = "BRIGHTON-QR-01") -> dict[str, object]:
    return {
        "distribution_id": distribution_id,
        "turnstile_token": "XXXX.DUMMY.TOKEN.XXXX",
        "audience": "recreation",
        "activity_context": "backcountry_snow",
        "tools": ["phone_apps", "radio"],
        "primary_hassle": "losing_service",
        "connectivity": "often",
        "tool_follow_up": "radio_only",
        "pain_follow_up": "communicate",
        "time_burden": None,
        "spend_band": "100_249",
        "concept_interest": "would_try",
        "contact_email": None,
        "contact_phone": None,
        "other_details": {},
        "questions_shown": [
            "audience",
            "activity_context",
            "tools",
            "connectivity",
            "primary_hassle",
            "tool_follow_up",
            "pain_follow_up",
            "spend_band",
            "concept_interest",
        ],
        "started_at": datetime.now(UTC).isoformat(),
        "completion_seconds": 58,
        "comment": "Make offline handoff easier.",
    }


@pytest.mark.asyncio
async def test_native_feedback_first_party_attribution_and_founder_access(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(
        "terrasatch.feedback.routes.create_session_factory",
        lambda settings: factory,
    )
    # Workspace login/session endpoints used by this test must share the same
    # in-memory SQLite factory instead of falling back to the default Postgres URL.
    monkeypatch.setattr(
        "terrasatch.workspace.routes.create_session_factory",
        lambda settings: factory,
    )

    async def limiter(*args, **kwargs):
        return None

    monkeypatch.setattr(
        "terrasatch.feedback.routes.enforce_public_rate_limit",
        limiter,
    )

    async def verify_turnstile(*args, **kwargs):
        return None

    monkeypatch.setattr(
        "terrasatch.feedback.routes._verify_turnstile",
        verify_turnstile,
    )

    async with factory() as session:
        account = Account(name="TerraSatch internal")
        session.add(account)
        await session.flush()
        org = Organization(
            account_id=account.id,
            name="Founding team",
            slug="founding-team",
        )
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

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        metadata = await client.get("/api/v1/feedback/forms/OUTFIELD-CHECKIN")
        assert metadata.status_code == 200
        assert metadata.json()["form_version"] == 3
        assert metadata.json()["adaptive"] is True
        assert metadata.json()["optional_contact"] is True
        assert metadata.json()["estimated_seconds"] == 60
        assert metadata.json()["advertising_trackers"] is False

        anonymous = await client.get("/api/v1/workspace/session")
        login = await client.post(
            "/api/v1/workspace/login",
            json={
                "email": "founder@example.test",
                "password": "Strong-test-password-2026!",
            },
            headers={"X-CSRF-Token": anonymous.json()["csrf_token"]},
        )
        assert login.status_code == 200
        csrf = login.json()["csrf_token"]

        created_distribution = await client.post(
            f"/api/v1/workspace/organizations/{org_id}/feedback/distributions",
            json={
                "distribution_id": "BRIGHTON-QR-01",
                "label": "Brighton poster QR",
                "channel": "qr",
                "placement": "Brighton",
                "audience_hint": "outdoor_recreation",
                "metadata": {"asset": "poster"},
            },
            headers={"X-CSRF-Token": csrf},
        )
        assert created_distribution.status_code == 201
        assert created_distribution.json()["path"] == "/check-in?d=BRIGHTON-QR-01"

        payload = recreation_payload()
        payload["contact_email"] = "qa@example.test"
        payload["contact_phone"] = "+1 555 010 2026"
        saved = await client.post(
            "/api/v1/feedback/forms/OUTFIELD-CHECKIN/responses",
            json=payload,
        )
        assert saved.status_code == 201
        assert saved.json()["form_id"] == "OUTFIELD-CHECKIN"
        assert saved.json()["form_version"] == 3
        assert saved.json()["distribution_id"] == "BRIGHTON-QR-01"

        unknown = recreation_payload("UNREGISTERED-QR")
        fallback = await client.post(
            "/api/v1/feedback/forms/OUTFIELD-CHECKIN/responses",
            json=unknown,
        )
        assert fallback.status_code == 201
        assert fallback.json()["distribution_id"] == "DIRECT"

        missing_turnstile = recreation_payload()
        missing_turnstile.pop("turnstile_token")
        rejected_turnstile = await client.post(
            "/api/v1/feedback/forms/OUTFIELD-CHECKIN/responses",
            json=missing_turnstile,
        )
        assert rejected_turnstile.status_code == 422

        too_fast = recreation_payload()
        too_fast["completion_seconds"] = 2
        rejected = await client.post(
            "/api/v1/feedback/forms/OUTFIELD-CHECKIN/responses",
            json=too_fast,
        )
        assert rejected.status_code == 422

        invalid_email = {**recreation_payload(), "contact_email": "not-an-email"}
        rejected_email = await client.post(
            "/api/v1/feedback/forms/OUTFIELD-CHECKIN/responses",
            json=invalid_email,
        )
        assert rejected_email.status_code == 422

        invalid_phone = {**recreation_payload(), "contact_phone": "123"}
        rejected_phone = await client.post(
            "/api/v1/feedback/forms/OUTFIELD-CHECKIN/responses",
            json=invalid_phone,
        )
        assert rejected_phone.status_code == 422

        missing_other_detail = {
            **recreation_payload(),
            "tools": ["phone_apps", "other"],
            "tool_follow_up": None,
            "other_details": {},
            "questions_shown": [
                "audience",
                "activity_context",
                "tools",
                "connectivity",
                "primary_hassle",
                "pain_follow_up",
                "spend_band",
                "concept_interest",
            ],
        }
        rejected_other = await client.post(
            "/api/v1/feedback/forms/OUTFIELD-CHECKIN/responses",
            json=missing_other_detail,
        )
        assert rejected_other.status_code == 422

        work_payload = {
            **recreation_payload(),
            "distribution_id": "BRIGHTON-QR-01",
            "audience": "work",
            "activity_context": "ski_patrol_avalanche",
            "tools": ["radio", "phone_apps"],
            "time_burden": "30_60m",
            "spend_band": "10k_25k",
            "questions_shown": [
                "audience",
                "activity_context",
                "tools",
                "connectivity",
                "primary_hassle",
                "tool_follow_up",
                "pain_follow_up",
                "time_burden",
                "spend_band",
                "concept_interest",
            ],
        }
        work_saved = await client.post(
            "/api/v1/feedback/forms/OUTFIELD-CHECKIN/responses",
            json=work_payload,
        )
        assert work_saved.status_code == 201

        async with factory() as session:
            rows = list(await session.scalars(select(SurveyResponse)))
            distributions = list(
                await session.scalars(select(FeedbackDistribution))
            )
            assert len(rows) == 3
            assert {row.form_id for row in rows} == {"OUTFIELD-CHECKIN"}
            assert {row.form_version for row in rows} == {3}
            assert {row.distribution_id for row in rows} == {
                "BRIGHTON-QR-01",
                "DIRECT",
            }
            contact_rows = [
                row
                for row in rows
                if row.answers.get("contact_email") or row.answers.get("contact_phone")
            ]
            assert len(contact_rows) == 1
            assert contact_rows[0].answers["contact_email"] == "qa@example.test"
            assert contact_rows[0].answers["contact_phone"] == "+1 555 010 2026"
            assert all(row.answers["questions_shown"] for row in rows)
            assert all(row.answers["branch_path"] for row in rows)
            assert all(row.answers["completion_seconds"] >= 5 for row in rows)
            assert {item.distribution_id for item in distributions} == {
                "BRIGHTON-QR-01",
            }

        summary = await client.get(
            f"/api/v1/workspace/organizations/{org_id}/feedback/summary"
        )
        assert summary.status_code == 200
        assert summary.json()["form"]["id"] == "OUTFIELD-CHECKIN"
        assert summary.json()["form"]["version"] == 3
        assert summary.json()["form"]["adaptive"] is True
        assert summary.json()["responses"] == 3
        assert summary.json()["contactable_responses"] == 1
        assert summary.json()["tools"]["radio"] == 3
        assert summary.json()["distribution"] == {
            "BRIGHTON-QR-01": 2,
            "DIRECT": 1,
        }

        filtered = await client.get(
            f"/api/v1/workspace/organizations/{org_id}/feedback/responses",
            params={"distribution_id": "BRIGHTON-QR-01"},
        )
        assert filtered.status_code == 200
        assert len(filtered.json()["responses"]) == 2

        export = await client.get(
            f"/api/v1/workspace/organizations/{org_id}/feedback/export.csv"
        )
        assert export.status_code == 200
        header = export.text.splitlines()[0].casefold()
        assert "form_id" in header
        assert "form_version" in header
        assert "distribution_id" in header
        assert "questions_shown" in header
        assert "branch_path" in header
        assert "completion_seconds" in header
        assert "contact_email" in header
        assert "contact_phone" in header

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        anonymous = await client.get("/api/v1/workspace/session")
        login = await client.post(
            "/api/v1/workspace/login",
            json={
                "email": "customer-owner@example.test",
                "password": "Strong-test-password-2026!",
            },
            headers={"X-CSRF-Token": anonymous.json()["csrf_token"]},
        )
        assert login.status_code == 200
        denied = await client.get(
            f"/api/v1/workspace/organizations/{org_id}/feedback/summary"
        )
        assert denied.status_code == 403

    await engine.dispose()


@pytest.mark.asyncio
async def test_turnstile_rejection_blocks_before_persistence(monkeypatch):
    """A failed Siteverify response must reject the public submission."""

    async def limiter(*args, **kwargs):
        return None

    monkeypatch.setattr(
        "terrasatch.feedback.routes.enforce_public_rate_limit",
        limiter,
    )

    class FailedVerificationResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"success": False, "error-codes": ["invalid-input-response"]}

    class FailedVerificationClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, *args, **kwargs):
            return FailedVerificationResponse()

    original_async_client = httpx.AsyncClient
    monkeypatch.setattr(
        "terrasatch.feedback.routes.httpx.AsyncClient",
        FailedVerificationClient,
    )

    app = create_app(
        Settings(
            environment="local",
            feedback_turnstile_secret_key="test-secret",
        )
    )

    payload = recreation_payload("DIRECT")
    async with original_async_client(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        rejected = await client.post(
            "/api/v1/feedback/forms/OUTFIELD-CHECKIN/responses",
            json=payload,
        )

    assert rejected.status_code == 400
    assert rejected.json()["detail"] == "Human verification failed. Please try again."

