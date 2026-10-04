"""Controlled Discovery workflow testing and human review API."""

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
from terrasatch.workspace.discovery import record_discovery_event


async def _login(client: httpx.AsyncClient, *, email: str, password: str) -> dict[str, str]:
    anonymous = await client.get("/api/v1/workspace/session")
    response = await client.post(
        "/api/v1/workspace/login",
        json={"email": email, "password": password},
        headers={"X-CSRF-Token": anonymous.json()["csrf_token"]},
    )
    assert response.status_code == 200
    return {"X-CSRF-Token": response.json()["csrf_token"]}


@pytest.mark.asyncio
async def test_controlled_discovery_testing_requires_human_start_measurement_and_review(
    monkeypatch,
) -> None:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(
        "terrasatch.workspace.routes.create_session_factory",
        lambda settings: factory,
    )

    owner_password = "Discovery-owner-password-2026!"
    operator_password = "Discovery-operator-password-2026!"
    workflow_key = "learn.signal.controlled-test"

    async with factory() as session:
        account = Account(name="Controlled Discovery account")
        session.add(account)
        await session.flush()
        organization = Organization(
            account_id=account.id,
            name="Controlled Discovery organization",
            slug=f"controlled-discovery-{uuid4().hex[:8]}",
        )
        owner = User(
            email=f"owner-{uuid4().hex[:8]}@example.com",
            display_name="Discovery owner",
            enabled=True,
            password_hash=hash_admin_password(owner_password),
            credential_version=1,
        )
        operator = User(
            email=f"operator-{uuid4().hex[:8]}@example.com",
            display_name="Discovery operator",
            enabled=True,
            password_hash=hash_admin_password(operator_password),
            credential_version=1,
        )
        session.add_all([organization, owner, operator])
        await session.flush()
        site = Site(
            organization_id=organization.id,
            name="Controlled Discovery site",
            slug=f"controlled-site-{uuid4().hex[:8]}",
        )
        session.add(site)
        session.add_all(
            [
                Membership(
                    organization_id=organization.id,
                    user_id=owner.id,
                    role=MembershipRole.OWNER,
                    enabled=True,
                ),
                Membership(
                    organization_id=organization.id,
                    user_id=operator.id,
                    role=MembershipRole.OPERATOR,
                    enabled=True,
                ),
            ]
        )
        await session.flush()
        candidate, _ = await record_discovery_event(
            session,
            organization_id=organization.id,
            site_id=site.id,
            event_type="workflow_identified",
            workflow_key=workflow_key,
            workflow_label="Candidate: Radio observation review",
            source_type="satchy_pattern_detector",
            source_ref=f"pattern:{workflow_key}",
            dedupe_key=f"auto:learn:{workflow_key}:support:3",
            confidence=0.65,
            evidence={
                "support_count": 3,
                "support_milestone": 3,
                "confidence_basis": "bounded_support_milestone_not_operational_truth",
            },
        )
        await session.commit()
        organization_id = organization.id
        owner_email = owner.email
        operator_email = operator.email
        candidate_id = candidate.id

    app = create_app(
        Settings(
            environment="local",
            admin_session_secret="controlled-discovery-session-secret",
            intelligence_provider="deterministic",
        )
    )
    base = f"/api/v1/workspace/organizations/{organization_id}/discovery"
    testing_url = f"{base}/workflows/{workflow_key}/testing"
    measurement_url = f"{testing_url}/measurements"
    review_url = f"{base}/workflows/{workflow_key}/review"

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as owner_client:
        owner_headers = await _login(
            owner_client,
            email=owner_email,
            password=owner_password,
        )
        request_id = uuid4()
        start_payload = {
            "request_id": str(request_id),
            "objective": "Measure whether the candidate reduces handoff duration.",
            "metric_key": "handoff_duration_seconds",
            "metric_unit": "seconds",
            "baseline_value": 10.0,
            "target_direction": "decrease",
            "sample_target": 2,
        }

        assert (await owner_client.post(testing_url, json=start_payload)).status_code == 403

        started = await owner_client.post(
            testing_url,
            json=start_payload,
            headers=owner_headers,
        )
        assert started.status_code == 201
        assert started.json()["duplicate"] is False
        testing_event = started.json()["event"]
        assert testing_event["event_type"] == "workflow_testing"
        assert testing_event["workflow_key"] == workflow_key
        assert testing_event["evidence"]["candidate_event_id"] == str(candidate_id)
        assert testing_event["evidence"]["measurement_count"] == 0
        assert testing_event["evidence"]["execution_authorized"] is False

        retry = await owner_client.post(
            testing_url,
            json=start_payload,
            headers=owner_headers,
        )
        assert retry.status_code == 201
        assert retry.json()["duplicate"] is True
        assert retry.json()["event"]["id"] == testing_event["id"]

        changed_retry = await owner_client.post(
            testing_url,
            json={**start_payload, "objective": "Changed objective"},
            headers=owner_headers,
        )
        assert changed_retry.status_code == 422
        assert "different test content" in changed_retry.json()["detail"]

        direct_state = await owner_client.post(
            f"{base}/events",
            json={
                "event_type": "workflow_approved",
                "workflow_key": workflow_key,
                "dedupe_key": f"manual:{workflow_key}:approved",
            },
            headers=owner_headers,
        )
        assert direct_state.status_code == 422
        assert "controlled Discovery workflow" in direct_state.json()["detail"]

        state_rollback = await owner_client.post(
            f"{base}/events",
            json={
                "event_type": "workflow_identified",
                "workflow_key": workflow_key,
                "workflow_label": "Attempted rollback",
                "dedupe_key": f"manual:{workflow_key}:identified-again",
            },
            headers=owner_headers,
        )
        assert state_rollback.status_code == 422
        assert "explicit revision" in state_rollback.json()["detail"]

        early_approval = await owner_client.post(
            review_url,
            json={
                "request_id": str(uuid4()),
                "decision": "approved",
                "rationale": "Trying to approve before measurement target.",
            },
            headers=owner_headers,
        )
        assert early_approval.status_code == 422
        assert "sample target" in early_approval.json()["detail"]

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as operator_client:
        operator_headers = await _login(
            operator_client,
            email=operator_email,
            password=operator_password,
        )
        measurement_one_id = uuid4()
        measurement_one = {
            "measurement_id": str(measurement_one_id),
            "value": 8.0,
            "note": "First controlled handoff sample",
            "source_ref": "field-test:sample-1",
        }
        first = await operator_client.post(
            measurement_url,
            json=measurement_one,
            headers=operator_headers,
        )
        assert first.status_code == 201
        assert first.json()["event"]["evidence"]["measurement_count"] == 1
        assert first.json()["event"]["evidence"]["measured_average"] == 8.0
        assert first.json()["event"]["evidence"]["observed_delta_from_baseline"] == -2.0
        assert first.json()["event"]["evidence"]["sample_target_met"] is False

        first_retry = await operator_client.post(
            measurement_url,
            json=measurement_one,
            headers=operator_headers,
        )
        assert first_retry.status_code == 201
        assert first_retry.json()["duplicate"] is True
        assert first_retry.json()["event"]["id"] == first.json()["event"]["id"]

        changed_measurement = await operator_client.post(
            measurement_url,
            json={**measurement_one, "value": 7.0},
            headers=operator_headers,
        )
        assert changed_measurement.status_code == 422
        assert "different content" in changed_measurement.json()["detail"]

        second = await operator_client.post(
            measurement_url,
            json={
                "measurement_id": str(uuid4()),
                "value": 6.0,
                "note": "Second controlled handoff sample",
                "source_ref": "field-test:sample-2",
            },
            headers=operator_headers,
        )
        assert second.status_code == 201
        evidence = second.json()["event"]["evidence"]
        assert evidence["measurement_count"] == 2
        assert evidence["measured_average"] == 7.0
        assert evidence["observed_delta_from_baseline"] == -3.0
        assert evidence["observed_delta_percent"] == -30.0
        assert evidence["sample_target_met"] is True
        assert evidence["execution_authorized"] is False

        extra = await operator_client.post(
            measurement_url,
            json={"measurement_id": str(uuid4()), "value": 5.0},
            headers=operator_headers,
        )
        assert extra.status_code == 422
        assert "sample target" in extra.json()["detail"]

        operator_review = await operator_client.post(
            review_url,
            json={
                "request_id": str(uuid4()),
                "decision": "approved",
                "rationale": "Operator should not be allowed to approve.",
            },
            headers=operator_headers,
        )
        assert operator_review.status_code == 403

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as owner_client:
        owner_headers = await _login(
            owner_client,
            email=owner_email,
            password=owner_password,
        )
        review_id = uuid4()
        approval_payload = {
            "request_id": str(review_id),
            "decision": "approved",
            "rationale": "Declared samples completed; reviewer accepts the test result.",
        }
        approved = await owner_client.post(
            review_url,
            json=approval_payload,
            headers=owner_headers,
        )
        assert approved.status_code == 201
        approved_event = approved.json()["event"]
        assert approved_event["event_type"] == "workflow_approved"
        assert approved_event["evidence"]["measurement_count"] == 2
        assert approved_event["evidence"]["measured_average"] == 7.0
        assert approved_event["evidence"]["execution_authorized"] is False

        approval_retry = await owner_client.post(
            review_url,
            json=approval_payload,
            headers=owner_headers,
        )
        assert approval_retry.status_code == 201
        assert approval_retry.json()["duplicate"] is True
        assert approval_retry.json()["event"]["id"] == approved_event["id"]

        summary = await owner_client.get(base)
        assert summary.status_code == 200
        assert summary.json()["workflow_counts"] == {
            "identified": 1,
            "testing": 0,
            "approved": 1,
            "rejected": 0,
        }
        assert summary.json()["phase_evidence"]["adapt"] is True

        cross_actor_retry = await owner_client.post(
            measurement_url,
            json=measurement_one,
            headers=owner_headers,
        )
        assert cross_actor_retry.status_code == 422
        assert "different actor" in cross_actor_retry.json()["detail"]

        after_review_measurement = await owner_client.post(
            measurement_url,
            json={"measurement_id": str(uuid4()), "value": 4.0},
            headers=owner_headers,
        )
        assert after_review_measurement.status_code == 422
        assert "must be in testing" in after_review_measurement.json()["detail"]

    await engine.dispose()

@pytest.mark.asyncio
async def test_openapi_exposes_controlled_discovery_testing_contract() -> None:
    app = create_app(
        Settings(
            environment="local",
            deployment_name="controlled-discovery-contract",
            api_base_url="http://testserver",
            intelligence_provider="deterministic",
            admin_session_secret="controlled-discovery-contract-secret",
        )
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    base = "/api/v1/workspace/organizations/{organization_id}/discovery/workflows"
    assert "post" in paths[f"{base}/{{workflow_key}}/testing"]
    assert "post" in paths[f"{base}/{{workflow_key}}/testing/measurements"]
    assert "post" in paths[f"{base}/{{workflow_key}}/review"]

