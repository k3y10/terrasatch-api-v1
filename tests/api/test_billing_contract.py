import httpx
import pytest
from pydantic import SecretStr

from terrasatch.config import Settings
from terrasatch.main import create_app


def make_settings() -> Settings:
    return Settings(
        environment="local",
        deployment_name="billing-contract-test",
        api_base_url="http://testserver",
        cors_origins=[],
        billing_enabled=False,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("plan_code", ["operations", "enterprise"])
async def test_scoped_plans_cannot_create_checkout(plan_code) -> None:
    settings = make_settings().model_copy(
        update={
            "billing_enabled": True,
            "stripe_secret_key": SecretStr("test-only"),
            "stripe_webhook_secret": SecretStr("test-only"),
            "billing_email_webhook_url": "https://example.com/email",
            "billing_email_webhook_secret": SecretStr("test-only"),
            "billing_activation_signing_secret": SecretStr("test-only"),
        }
    )
    transport = httpx.ASGITransport(app=create_app(settings))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/v1/billing/checkout",
            json={
                "display_name": "Test Operator",
                "email": "operator@example.com",
                "organization_name": "Test Operations",
                "plan_code": plan_code,
                "billing_interval": "monthly",
            },
        )
    assert response.status_code == 400
    assert "not available for self-service" in response.text


@pytest.mark.asyncio
async def test_openapi_exposes_billing_routes() -> None:
    application = create_app(make_settings())
    transport = httpx.ASGITransport(app=application)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "get" in paths["/api/v1/billing/plans"]
    assert "post" in paths["/api/v1/billing/checkout"]
    assert "get" in paths["/api/v1/billing/checkout/status"]
    assert "get" in paths["/api/v1/billing/subscription"]
    assert "post" in paths["/api/v1/billing/portal"]
    assert "post" in paths["/api/v1/billing/activate"]
    assert "post" in paths["/api/v1/billing/stripe/webhook"]


@pytest.mark.asyncio
async def test_plan_catalog_is_public_and_hides_stripe_ids() -> None:
    application = create_app(make_settings())
    transport = httpx.ASGITransport(app=application)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/v1/billing/plans")

    assert response.status_code == 200
    payload = response.json()
    assert [plan["code"] for plan in payload] == ["field", "team", "operations", "enterprise"]
    assert payload[1]["recommended"] is True
    assert payload[1]["trial_days"] == 30
    assert payload[1]["monthly_amount_cents"] == 39_900
    serialized = response.text.casefold()
    assert "lookup_key" not in serialized
    assert "price_" not in serialized


@pytest.mark.asyncio
async def test_checkout_is_fail_closed_when_billing_is_disabled() -> None:
    application = create_app(make_settings())
    transport = httpx.ASGITransport(app=application)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/v1/billing/checkout",
            json={
                "display_name": "Test Operator",
                "email": "operator@example.com",
                "organization_name": "Example Mountain Ops",
                "plan_code": "team",
                "billing_interval": "monthly",
            },
        )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "provider_unavailable"


@pytest.mark.asyncio
async def test_subscription_requires_tenant_credentials() -> None:
    application = create_app(make_settings())
    transport = httpx.ASGITransport(app=application)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/v1/billing/subscription")

    assert response.status_code == 401
    assert response.json()["detail"] == "Bearer token required"


@pytest.mark.asyncio
async def test_webhook_rejects_missing_signature_before_provider_or_database_work() -> None:
    application = create_app(make_settings())
    transport = httpx.ASGITransport(app=application)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post("/api/v1/billing/stripe/webhook", content=b"{}")

    assert response.status_code == 400
    assert response.json()["detail"] == "Stripe-Signature header required"


@pytest.mark.asyncio
async def test_public_reference_lists_billing_contract_and_rate_limit_error() -> None:
    application = create_app(make_settings())
    transport = httpx.ASGITransport(app=application)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/v1/reference")

    assert response.status_code == 200
    payload = response.json()
    catalog = {(item["method"], item["path"]) for item in payload["endpoints"]}
    assert ("GET", "/api/v1/billing/plans") in catalog
    assert ("POST", "/api/v1/billing/checkout") in catalog
    assert ("GET", "/api/v1/billing/checkout/status") in catalog
    assert ("GET", "/api/v1/billing/subscription") in catalog
    assert ("POST", "/api/v1/billing/portal") in catalog
    assert ("POST", "/api/v1/billing/activate") in catalog
    assert ("POST", "/api/v1/billing/stripe/webhook") in catalog
    errors = {(item["http_status"], item["code"]) for item in payload["common_errors"]}
    assert (429, "rate_limited") in errors
    assert (503, "provider_unavailable") in errors


@pytest.mark.asyncio
async def test_workspace_webhook_alias_is_not_exposed_outside_staging() -> None:
    application = create_app(make_settings())
    transport = httpx.ASGITransport(app=application)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/v1/workspace/billing/stripe/webhook",
            content=b"{}",
        )

    assert response.status_code == 404
    assert "/api/v1/workspace/billing/stripe/webhook" not in application.openapi()["paths"]


@pytest.mark.asyncio
async def test_workspace_webhook_alias_is_exposed_only_in_staging() -> None:
    settings = Settings(
        environment="staging",
        deployment_name="billing-staging-contract-test",
        api_base_url="https://staging-api.terrasatch.com",
        cors_origins=[],
        billing_enabled=False,
    )
    application = create_app(settings)
    transport = httpx.ASGITransport(app=application)

    assert "/api/v1/workspace/billing/stripe/webhook" in application.openapi()["paths"]
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/v1/workspace/billing/stripe/webhook",
            content=b'{"id":"evt_test_staging"}',
        )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "provider_unavailable"


@pytest.mark.asyncio
async def test_staging_billing_callback_pages_are_self_contained() -> None:
    settings = Settings(
        environment="staging",
        deployment_name="billing-staging-callback-test",
        api_base_url="https://staging-api.terrasatch.com",
        cors_origins=[],
        billing_enabled=False,
    )
    application = create_app(settings)
    transport = httpx.ASGITransport(app=application)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        success = await client.get("/api/v1/workspace/billing/success")
        cancel = await client.get("/api/v1/workspace/billing/cancel")
        portal_return = await client.get("/api/v1/workspace/billing/portal-return")
        activate = await client.get("/api/v1/workspace/billing/activate")

    assert success.status_code == 200
    assert "workspace/billing/checkout/status" in success.text
    assert "workspace/billing/checkout/activation" in success.text
    assert "data.state === \"ready\"" in success.text
    assert "Create access &amp; open workspace" in success.text
    assert 'fetch("/api/v1/workspace/login"' in success.text
    assert 'location.replace("/portal")' in success.text
    assert 'href="/api/v1/workspace/billing/activate#token="' not in success.text
    assert success.headers["cache-control"] == "no-store"
    assert cancel.status_code == 200
    assert "No changes were made." in cancel.text
    assert "Return to plans" in cancel.text
    assert portal_return.status_code == 200
    assert "Billing settings updated" in portal_return.text
    assert 'href="/portal"' in portal_return.text
    assert activate.status_code == 200
    assert "workspace/billing/activate" in activate.text
    assert "Create your TerraSatch password" in activate.text


@pytest.mark.asyncio
async def test_signed_received_email_webhook_reaches_transactional_workspace_storage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import base64
    import hashlib
    import hmac
    import json
    from datetime import UTC, datetime

    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from terrasatch.api import billing as billing_api
    from terrasatch.database.base import Base
    from terrasatch.workspace.email_models import WorkspaceEmailMessage
    from terrasatch.workspace.email_service import InboundEmailResult

    secret_bytes = b"terrasatch-route-webhook-test"
    webhook_secret = SecretStr(
        "whsec_" + base64.b64encode(secret_bytes).decode("ascii")
    )
    settings = Settings(
        environment="staging",
        deployment_name="email-webhook-route-test",
        api_base_url="https://staging-api.terrasatch.com",
        cors_origins=[],
        resend_webhook_secret=webhook_secret,
    )

    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(billing_api, "create_session_factory", lambda _settings: factory)

    async def persist_received_email(
        session,
        _settings,
        *,
        event: dict[str, object],
        webhook_id: str,
    ) -> InboundEmailResult:
        data = event["data"]
        assert isinstance(data, dict)
        message = WorkspaceEmailMessage(
            provider_email_id=str(data["email_id"]),
            provider_event_id=webhook_id,
            direction="inbound",
            received_for="keaton@terrasatch.com",
            from_address="partner@example.com",
            to_addresses=["keaton@terrasatch.com"],
            cc_addresses=[],
            bcc_addresses=[],
            reply_to=[],
            subject="Signed route test",
            text_body="Persisted through the webhook transaction.",
            html_body=None,
            headers={},
            attachments=[],
            received_at=datetime.now(UTC),
        )
        session.add(message)
        await session.flush()
        return InboundEmailResult(True, False, "email.received", message.id)

    monkeypatch.setattr(
        billing_api,
        "ingest_resend_received_email",
        persist_received_email,
    )

    event = {
        "type": "email.received",
        "created_at": "2026-09-26T05:00:00Z",
        "data": {
            "email_id": "email_route_inbound_1",
            "from": "partner@example.com",
            "to": ["keaton@terrasatch.com"],
            "subject": "Signed route test",
        },
    }
    payload = json.dumps(event, separators=(",", ":")).encode("utf-8")
    webhook_id = "msg_route_inbound_1"
    timestamp = str(int(datetime.now(UTC).timestamp()))
    signed = f"{webhook_id}.{timestamp}.".encode() + payload
    signature = base64.b64encode(
        hmac.new(secret_bytes, signed, hashlib.sha256).digest()
    ).decode("ascii")

    application = create_app(settings)
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/api/v1/workspace/billing/resend/webhook",
            content=payload,
            headers={
                "content-type": "application/json",
                "svix-id": webhook_id,
                "svix-timestamp": timestamp,
                "svix-signature": f"v1,{signature}",
            },
        )

    assert response.status_code == 200
    assert response.json() == {"matched": True, "duplicate": False}

    async with factory() as session:
        stored = await session.scalar(
            select(WorkspaceEmailMessage).where(
                WorkspaceEmailMessage.provider_email_id == "email_route_inbound_1"
            )
        )
        assert stored is not None
        assert stored.provider_event_id == webhook_id
        assert stored.received_for == "keaton@terrasatch.com"

    await engine.dispose()


@pytest.mark.asyncio
async def test_resend_webhook_routes_are_scoped_and_disabled_without_secret() -> None:
    settings = Settings(
        environment="staging",
        deployment_name="billing-resend-contract-test",
        api_base_url="https://staging-api.terrasatch.com",
        cors_origins=[],
    )
    application = create_app(settings)
    paths = application.openapi()["paths"]

    assert "/api/v1/billing/resend/webhook" in paths
    assert "/api/v1/workspace/billing/resend/webhook" in paths

    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/api/v1/workspace/billing/resend/webhook",
            content=b"{}",
        )

    assert response.status_code == 404
