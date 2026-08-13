import httpx
import pytest

from terrasatch.config import Settings
from terrasatch.main import create_app


def make_settings() -> Settings:
    return Settings(
        environment="local",
        deployment_name="radio-contract-test",
        api_base_url="http://testserver",
        cors_origins=[],
        intelligence_provider="deterministic",
    )


@pytest.mark.asyncio
async def test_openapi_exposes_radio_intelligence_resources() -> None:
    application = create_app(make_settings())
    transport = httpx.ASGITransport(app=application)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/v1/agents" in paths
    assert "/api/v1/channels" in paths
    assert "/api/v1/callsigns" in paths
    assert "/api/v1/transmissions" in paths
    assert "/api/v1/transcripts" in paths
    assert "/api/v1/events" in paths


@pytest.mark.asyncio
async def test_radio_resources_require_bearer_credentials() -> None:
    application = create_app(make_settings())
    transport = httpx.ASGITransport(app=application)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/v1/events")

    assert response.status_code == 401
    assert response.json()["detail"] == "Bearer token required"


@pytest.mark.asyncio
async def test_public_reference_mentions_realtime_and_event_routes() -> None:
    application = create_app(make_settings())
    transport = httpx.ASGITransport(app=application)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/v1/reference")

    assert response.status_code == 200
    catalog = {(item["method"], item["path"]) for item in response.json()["endpoints"]}
    assert ("POST", "/api/v1/transmissions") in catalog
    assert ("GET", "/api/v1/events") in catalog
    assert ("WS", "/ws/v1/events") in catalog
