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
async def test_openapi_exposes_complete_radio_intelligence_resources() -> None:
    application = create_app(make_settings())
    transport = httpx.ASGITransport(app=application)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert {"get", "post"}.issubset(paths["/api/v1/agents"])
    assert {"get", "patch"}.issubset(paths["/api/v1/agents/{agent_id}"])
    assert {"get", "post"}.issubset(paths["/api/v1/channels"])
    assert {"get", "patch"}.issubset(paths["/api/v1/channels/{channel_id}"])
    assert {"get", "post"}.issubset(paths["/api/v1/callsigns"])
    assert {"get", "patch"}.issubset(paths["/api/v1/callsigns/{callsign_id}"])
    assert {"get", "post"}.issubset(paths["/api/v1/transmissions"])
    assert "get" in paths["/api/v1/transmissions/{transmission_id}"]
    assert "get" in paths["/api/v1/transcripts"]
    assert "get" in paths["/api/v1/transcripts/{transcript_id}"]
    assert "get" in paths["/api/v1/events"]
    assert "get" in paths["/api/v1/events/{event_id}"]


@pytest.mark.asyncio
async def test_radio_resources_require_bearer_credentials() -> None:
    application = create_app(make_settings())
    transport = httpx.ASGITransport(app=application)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/v1/events")

    assert response.status_code == 401
    assert response.json()["detail"] == "Bearer token required"


@pytest.mark.asyncio
async def test_public_reference_matches_detail_and_realtime_routes() -> None:
    application = create_app(make_settings())
    transport = httpx.ASGITransport(app=application)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/v1/reference")

    assert response.status_code == 200
    catalog = {(item["method"], item["path"]) for item in response.json()["endpoints"]}
    assert ("POST", "/api/v1/transmissions") in catalog
    assert ("GET", "/api/v1/transmissions/{transmission_id}") in catalog
    assert ("GET", "/api/v1/transcripts/{transcript_id}") in catalog
    assert ("GET", "/api/v1/events/{event_id}") in catalog
    assert ("PATCH", "/api/v1/agents/{agent_id}") in catalog
    assert ("PATCH", "/api/v1/channels/{channel_id}") in catalog
    assert ("PATCH", "/api/v1/callsigns/{callsign_id}") in catalog
    assert ("WS", "/ws/v1/events") in catalog

    errors = {(item["http_status"], item["code"]) for item in response.json()["common_errors"]}
    assert (404, "not_found") in errors
    assert (409, "resource_conflict") in errors
