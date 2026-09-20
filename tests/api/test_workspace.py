"""Authentication and tenant isolation against a real local SQL database."""

from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from terrasatch.admin.security import hash_admin_password
from terrasatch.billing.models import BillingCustomer
from terrasatch.config import Settings
from terrasatch.database.base import Base
from terrasatch.identity.models import (
    Account,
    Membership,
    MembershipRole,
    Organization,
    Site,
    Team,
    User,
)
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
            credential_version=1,
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
        await session.flush()
        team = Team(organization_id=org.id, site_id=site.id, name="Field team", enabled=True)
        session.add(team)
        session.add(
            BillingCustomer(
                account_id=account.id,
                organization_id=org.id,
                stripe_customer_id="cus_workspace_portal_test",
            )
        )
        await session.commit()
        site_id = site.id
        team_id = team.id
        organization_id, user_id = org.id, user.id
    app = create_app(
        Settings(
            environment="local",
            admin_session_secret="test-only-session-secret",
            intelligence_provider="ollama",
            billing_enabled=True,
            stripe_secret_key=SecretStr("sk_test_workspace_portal"),
        )
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

        async def fake_portal(self, *, stripe_customer_id: str) -> str:
            assert stripe_customer_id == "cus_workspace_portal_test"
            return "https://billing.stripe.com/p/session?secret=test_workspace_portal"

        monkeypatch.setattr(
            "terrasatch.workspace.routes.StripeGateway.create_customer_portal",
            fake_portal,
        )
        assert (
            await client.post(
                f"/api/v1/workspace/organizations/{organization_id}/billing"
            )
        ).status_code == 403
        portal = await client.post(
            f"/api/v1/workspace/organizations/{organization_id}/billing",
            headers=headers,
        )
        assert portal.status_code == 200
        assert portal.json() == {
            "url": "https://billing.stripe.com/p/session?secret=test_workspace_portal"
        }

        assert own.json()["modules"] == ["Map", "Radio Log", "Observations", "Satchy"]
        assert own.json()["integrations"]["devices"] == []
        assert own.json()["teams"] == [
            {"id": str(team_id), "name": "Field team", "site_id": str(site_id)}
        ]
        catalog = own.json()["integrations"]["catalog"]
        assert {provider["key"] for provider in catalog} >= {
            "terrasatch_edge",
            "google_drive",
            "slack",
            "garmin",
            "alltrails",
        }
        setup = {provider["key"]: provider["setup_status"] for provider in catalog}
        assert setup["google_drive"] == "planned"
        assert setup["slack"] == "planned"
        assert own.json()["integrations"]["connections"] == []

        integration_url = f"/api/v1/workspace/organizations/{organization_id}/integrations"
        assert (await client.post(
            integration_url,
            json={"provider": "google_drive", "scope": "user"},
        )).status_code == 403

        personal = await client.post(
            integration_url,
            json={
                "provider": "google_drive",
                "scope": "user",
                "display_name": "My field Drive",
                "configuration": {"folder_id": "folder-test-123"},
            },
            headers=headers,
        )
        assert personal.status_code == 201
        assert personal.json()["scope"] == "user"
        assert personal.json()["owner_user_id"] == str(user_id)
        assert personal.json()["status"] == "requested"

        team_connection = await client.post(
            integration_url,
            json={
                "provider": "slack",
                "scope": "team",
                "team_id": str(team_id),
                "display_name": "Field team Slack",
            },
            headers=headers,
        )
        assert team_connection.status_code == 201
        assert team_connection.json()["team_id"] == str(team_id)

        organization_connection = await client.post(
            integration_url,
            json={"provider": "snowflake", "scope": "organization"},
            headers=headers,
        )
        assert organization_connection.status_code == 201
        assert organization_connection.json()["scope"] == "organization"

        duplicate = await client.post(
            integration_url,
            json={"provider": "google_drive", "scope": "user"},
            headers=headers,
        )
        assert duplicate.status_code == 409

        secret_rejected = await client.post(
            integration_url,
            json={
                "provider": "mapbox",
                "scope": "user",
                "configuration": {"api_token": "must-not-be-stored"},
            },
            headers=headers,
        )
        assert secret_rejected.status_code == 400

        managed_rejected = await client.post(
            integration_url,
            json={"provider": "terrasatch_edge", "scope": "organization"},
            headers=headers,
        )
        assert managed_rejected.status_code == 400

        with_integrations = (
            await client.get(f"/api/v1/workspace/organizations/{organization_id}")
        ).json()
        assert len(with_integrations["integrations"]["connections"]) == 3

        satchy_request_id = uuid4()
        proposal = await client.post(
            f"/api/v1/workspace/organizations/{organization_id}/chat",
            json={
                "request_id": str(satchy_request_id),
                "site_id": str(site_id),
                "message": "Satchy, notify the team that staging integration review is ready.",
            },
            headers=headers,
        )
        assert proposal.status_code == 200
        assert proposal.json()["action_id"] == str(satchy_request_id)
        assert proposal.json()["action_status"] == "awaiting_approval"
        assert proposal.json()["approval_required"] is True
        assert "Nothing has been sent" in proposal.json()["answer"]

        proposed_workspace = (
            await client.get(f"/api/v1/workspace/organizations/{organization_id}")
        ).json()
        proposed_action = next(
            item
            for item in proposed_workspace["actions"]
            if item["id"] == str(satchy_request_id)
        )
        assert proposed_action["source_id"] is None
        assert proposed_action["status"] == "awaiting_approval"

        approved_action = await client.post(
            (
                f"/api/v1/workspace/organizations/{organization_id}/actions/"
                f"{satchy_request_id}"
            ),
            json={"decision": "approve"},
            headers=headers,
        )
        assert approved_action.status_code == 200
        assert approved_action.json()["status"] == "approved"
        assert approved_action.json()["integration_execution"]["status"] == "blocked"

        revoked = await client.post(
            f"{integration_url}/{personal.json()['id']}/revoke",
            headers=headers,
        )
        assert revoked.status_code == 200
        assert revoked.json()["status"] == "revoked"
        assert revoked.json()["enabled"] is False

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

        asset_payload = {
            "name": "Cardiff Camera",
            "asset_type": "camera",
            "provider": "camera-provider",
            "site_id": str(site_id),
            "owner_user_id": str(user_id),
            "capabilities": [" Camera:Capture ", "camera:capture"],
            "state": "available",
            "location": {"label": "Cardiff Bowl"},
            "policy": {"mission_execution_enabled": False},
        }
        created_asset = await client.post(
            f"/api/v1/workspace/organizations/{organization_id}/assets",
            json=asset_payload,
            headers=headers,
        )
        assert created_asset.status_code == 201
        asset = created_asset.json()
        assert asset["site_id"] == str(site_id)
        assert asset["owner_user_id"] == str(user_id)
        assert asset["capabilities"] == ["camera:capture"]
        assert asset["state"] == "available"

        visible_assets = (
            await client.get(f"/api/v1/workspace/organizations/{organization_id}")
        ).json()["assets"]
        assert [item["id"] for item in visible_assets] == [asset["id"]]

        inventory = await client.get(
            f"/api/v1/workspace/organizations/{organization_id}/assets"
        )
        assert inventory.status_code == 200
        assert [item["id"] for item in inventory.json()] == [asset["id"]]

        patched_asset = await client.patch(
            f"/api/v1/workspace/organizations/{organization_id}/assets/{asset['id']}",
            json={"state": "busy", "location": {"label": "Cardiff Bowl", "source": "workspace"}},
            headers=headers,
        )
        assert patched_asset.status_code == 200
        assert patched_asset.json()["state"] == "busy"
        assert patched_asset.json()["location"]["source"] == "workspace"

        bad_asset = await client.post(
            f"/api/v1/workspace/organizations/{organization_id}/assets",
            json={
                **asset_payload,
                "name": "Foreign Site Camera",
                "site_id": str(uuid4()),
            },
            headers=headers,
        )
        assert bad_asset.status_code == 404
        async with factory() as session:
            user = await session.get(User, user_id)
            user.enabled = False
            await session.commit()
        assert (
            await client.get(f"/api/v1/workspace/organizations/{organization_id}")
        ).status_code == 401
    await engine.dispose()
