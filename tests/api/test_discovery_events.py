"""Evidence-backed Discovery event storage, derivation, and workspace API."""

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
from terrasatch.workspace.discovery import (
    discovery_evidence_summary,
    list_discovery_events,
    record_discovery_event,
)


@pytest.mark.asyncio
async def test_discovery_summary_uses_latest_unique_workflow_evidence() -> None:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        account = Account(name="Discovery account")
        session.add(account)
        await session.flush()
        organization = Organization(
            account_id=account.id,
            name="Discovery organization",
            slug="discovery",
        )
        user = User(
            email="discovery@example.com",
            display_name="Discovery operator",
            enabled=True,
        )
        session.add_all([organization, user])
        await session.flush()
        site = Site(
            organization_id=organization.id,
            name="Discovery site",
            slug="discovery-site",
        )
        session.add(site)
        await session.flush()

        await record_discovery_event(
            session,
            organization_id=organization.id,
            site_id=site.id,
            actor_user_id=user.id,
            event_type="signal_observed",
            source_type="radio",
            source_ref="tx-1",
            dedupe_key="signal:tx-1",
            confidence=0.98,
            evidence={"channel": "field"},
        )
        await record_discovery_event(
            session,
            organization_id=organization.id,
            site_id=site.id,
            actor_user_id=user.id,
            event_type="context_observed",
            source_type="workspace",
            source_ref="map-1",
            dedupe_key="context:map-1",
        )
        identified, _ = await record_discovery_event(
            session,
            organization_id=organization.id,
            event_type="workflow_identified",
            source_type="satchy",
            workflow_key="radio_to_record",
            workflow_label="Radio observation to record",
            dedupe_key="workflow:radio_to_record:identified",
            evidence={"steps": ["radio", "record"]},
        )
        revised, revised_duplicate = await record_discovery_event(
            session,
            organization_id=organization.id,
            event_type="workflow_identified",
            source_type="satchy",
            workflow_key="radio_to_record",
            workflow_label="Radio to supervisor review to record",
            dedupe_key="workflow:radio_to_record:identified:v2",
            evidence={"steps": ["radio", "supervisor_review", "record"]},
            supersedes_event_id=identified.id,
        )
        assert revised_duplicate is False
        assert revised.supersedes_event_id == identified.id

        with pytest.raises(ValueError, match="same workflow_key"):
            await record_discovery_event(
                session,
                organization_id=organization.id,
                event_type="workflow_identified",
                source_type="satchy",
                workflow_key="different_workflow",
                dedupe_key="workflow:different:bad-revision",
                supersedes_event_id=identified.id,
            )

        with pytest.raises(ValueError, match="not found in this organization"):
            await record_discovery_event(
                session,
                organization_id=uuid4(),
                event_type="workflow_identified",
                source_type="satchy",
                workflow_key="radio_to_record",
                dedupe_key="workflow:cross-org:bad-revision",
                supersedes_event_id=revised.id,
            )

        with pytest.raises(ValueError, match="already been superseded"):
            await record_discovery_event(
                session,
                organization_id=organization.id,
                event_type="workflow_identified",
                source_type="satchy",
                workflow_key="radio_to_record",
                dedupe_key="workflow:radio_to_record:branch",
                supersedes_event_id=identified.id,
            )

        testing, duplicate = await record_discovery_event(
            session,
            organization_id=organization.id,
            event_type="workflow_testing",
            source_type="satchy",
            workflow_key="radio_to_record",
            dedupe_key="workflow:radio_to_record:testing",
        )
        retry, duplicate_retry = await record_discovery_event(
            session,
            organization_id=organization.id,
            event_type="workflow_testing",
            source_type="satchy",
            workflow_key="radio_to_record",
            dedupe_key="workflow:radio_to_record:testing",
        )
        assert duplicate is False
        assert duplicate_retry is True
        assert retry.id == testing.id

        approved_event, _ = await record_discovery_event(
            session,
            organization_id=organization.id,
            event_type="workflow_approved",
            source_type="manual",
            actor_user_id=user.id,
            workflow_key="radio_to_record",
            dedupe_key="workflow:radio_to_record:approved",
        )
        late_revision, _ = await record_discovery_event(
            session,
            organization_id=organization.id,
            event_type="workflow_identified",
            source_type="satchy",
            workflow_key="radio_to_record",
            workflow_label="Radio to supervisor review to archived record",
            dedupe_key="workflow:radio_to_record:identified:v3",
            evidence={
                "steps": [
                    "radio",
                    "supervisor_review",
                    "archived_record",
                ]
            },
            supersedes_event_id=revised.id,
        )
        assert late_revision.supersedes_event_id == revised.id
        assert approved_event.id != late_revision.id
        await record_discovery_event(
            session,
            organization_id=organization.id,
            event_type="workflow_identified",
            source_type="satchy",
            workflow_key="shift_handoff",
            workflow_label="Shift handoff summary",
            dedupe_key="workflow:shift_handoff:identified",
        )
        await record_discovery_event(
            session,
            organization_id=organization.id,
            event_type="workflow_rejected",
            source_type="manual",
            actor_user_id=user.id,
            workflow_key="shift_handoff",
            workflow_label="Shift handoff summary",
            dedupe_key="workflow:shift_handoff:rejected",
        )
        await session.commit()

        summary = await discovery_evidence_summary(
            session,
            organization_id=organization.id,
        )
        assert summary["event_count"] == 9
        assert summary["active_event_count"] == 7
        assert summary["signal_count"] == 1
        assert summary["context_count"] == 1
        assert summary["workflow_counts"] == {
            "identified": 2,
            "testing": 0,
            "approved": 1,
            "rejected": 1,
        }
        assert summary["phase_evidence"] == {
            "listen": True,
            "watch": True,
            "learn": True,
            "adapt": True,
        }
        states = {item["key"]: item["state"] for item in summary["workflows"]}
        assert states == {
            "radio_to_record": "approved",
            "shift_handoff": "rejected",
        }
        labels = {item["key"]: item["label"] for item in summary["workflows"]}
        assert labels["radio_to_record"] == "Radio to supervisor review to archived record"

        approved = await list_discovery_events(
            session,
            organization_id=organization.id,
            event_type="workflow_approved",
        )
        assert [event.workflow_key for event in approved] == ["radio_to_record"]

    await engine.dispose()


@pytest.mark.asyncio
async def test_discovery_workspace_api_is_tenant_scoped_and_admin_written(monkeypatch) -> None:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(
        "terrasatch.workspace.routes.create_session_factory",
        lambda settings: factory,
    )

    async with factory() as session:
        account = Account(name="Discovery API account")
        session.add(account)
        await session.flush()
        organization = Organization(
            account_id=account.id,
            name="Discovery API organization",
            slug="discovery-api",
        )
        user = User(
            email="discovery-api@example.com",
            display_name="Discovery API owner",
            enabled=True,
            password_hash=hash_admin_password("Discovery-test-password-2026!"),
            credential_version=1,
        )
        session.add_all([organization, user])
        await session.flush()
        session.add(
            Membership(
                organization_id=organization.id,
                user_id=user.id,
                role=MembershipRole.OWNER,
                enabled=True,
            )
        )
        site = Site(
            organization_id=organization.id,
            name="Discovery API site",
            slug="discovery-api-site",
        )
        session.add(site)
        await session.commit()
        organization_id = organization.id
        site_id = site.id

    app = create_app(
        Settings(
            environment="local",
            admin_session_secret="discovery-api-session-secret",
            intelligence_provider="deterministic",
        )
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        summary_url = f"/api/v1/workspace/organizations/{organization_id}/discovery"
        events_url = f"{summary_url}/events"

        assert (await client.get(summary_url)).status_code == 401
        anonymous = await client.get("/api/v1/workspace/session")
        login = await client.post(
            "/api/v1/workspace/login",
            json={
                "email": "discovery-api@example.com",
                "password": "Discovery-test-password-2026!",
            },
            headers={"X-CSRF-Token": anonymous.json()["csrf_token"]},
        )
        assert login.status_code == 200
        headers = {"X-CSRF-Token": login.json()["csrf_token"]}

        empty = await client.get(summary_url)
        assert empty.status_code == 200
        assert empty.json()["event_count"] == 0
        assert empty.json()["active_event_count"] == 0

        payload = {
            "event_type": "workflow_identified",
            "site_id": str(site_id),
            "workflow_key": "radio_to_record",
            "workflow_label": "Radio observation to record",
            "dedupe_key": "manual:radio_to_record:identified",
            "confidence": 0.9,
            "evidence": {"reason": "Repeated field handoff"},
        }
        assert (await client.post(events_url, json=payload)).status_code == 403

        created = await client.post(events_url, json=payload, headers=headers)
        assert created.status_code == 201
        assert created.json()["duplicate"] is False
        event_id = created.json()["event"]["id"]

        revised_payload = {
            **payload,
            "workflow_label": "Radio to supervisor review to record",
            "dedupe_key": "manual:radio_to_record:identified:v2",
            "supersedes_event_id": event_id,
            "evidence": {
                "reason": "Supervisor review observed",
                "steps": ["radio", "supervisor_review", "record"],
            },
        }
        revised = await client.post(events_url, json=revised_payload, headers=headers)
        assert revised.status_code == 201
        assert revised.json()["duplicate"] is False
        assert revised.json()["event"]["supersedes_event_id"] == event_id

        revised_retry = await client.post(
            events_url,
            json=revised_payload,
            headers=headers,
        )
        assert revised_retry.status_code == 201
        assert revised_retry.json()["duplicate"] is True
        assert revised_retry.json()["event"]["id"] == revised.json()["event"]["id"]

        branch = await client.post(
            events_url,
            json={
                **revised_payload,
                "dedupe_key": "manual:radio_to_record:identified:branch",
            },
            headers=headers,
        )
        assert branch.status_code == 422
        assert "already been superseded" in branch.json()["detail"]

        retry = await client.post(events_url, json=payload, headers=headers)
        assert retry.status_code == 201
        assert retry.json()["duplicate"] is True
        assert retry.json()["event"]["id"] == event_id

        dedupe_collision = await client.post(
            events_url,
            json={
                **payload,
                "workflow_label": "Changed content with reused retry key",
            },
            headers=headers,
        )
        assert dedupe_collision.status_code == 422
        assert "dedupe_key is already used" in dedupe_collision.json()["detail"]

        invalid = await client.post(
            events_url,
            json={"event_type": "workflow_testing"},
            headers=headers,
        )
        assert invalid.status_code == 422

        summary = await client.get(summary_url)
        assert summary.status_code == 200
        assert summary.json()["event_count"] == 2
        assert summary.json()["active_event_count"] == 1
        assert summary.json()["workflow_counts"] == {
            "identified": 1,
            "testing": 0,
            "approved": 0,
            "rejected": 0,
        }
        assert summary.json()["phase_evidence"]["learn"] is True
        assert summary.json()["workflows"][0]["label"] == (
            "Radio to supervisor review to record"
        )

        events = await client.get(events_url)
        assert events.status_code == 200
        assert len(events.json()) == 2
        assert events.json()[0]["workflow_key"] == "radio_to_record"
        assert events.json()[0]["supersedes_event_id"] == event_id

        other = await client.get(
            f"/api/v1/workspace/organizations/{uuid4()}/discovery"
        )
        assert other.status_code == 404

    await engine.dispose()


@pytest.mark.asyncio
async def test_openapi_exposes_discovery_evidence_contract() -> None:
    app = create_app(
        Settings(
            environment="local",
            deployment_name="discovery-events-contract",
            api_base_url="http://testserver",
            intelligence_provider="deterministic",
            admin_session_secret="discovery-events-session-secret",
        )
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    base = "/api/v1/workspace/organizations/{organization_id}/discovery"
    assert "get" in paths[base]
    assert "get" in paths[f"{base}/events"]
    assert "post" in paths[f"{base}/events"]
