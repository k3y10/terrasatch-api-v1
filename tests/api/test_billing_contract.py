import httpx
import pytest

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
    assert payload[1]["monthly_amount_cents"] == 34_900
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
