import httpx
import pytest

from terrasatch.config import Settings
from terrasatch.main import create_app


def make_settings(*, docs_enabled: bool = True) -> Settings:
    return Settings(
        environment="local",
        deployment_name="landing-test",
        api_base_url="http://testserver",
        cors_origins=[],
        enable_docs=docs_enabled,
    )


@pytest.mark.asyncio
async def test_root_serves_branded_terrasatch_status_page() -> None:
    application = create_app(make_settings())
    transport = httpx.ASGITransport(app=application)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "TerraSatch API" in response.text
    assert "Terrain Intelligence" in response.text
    assert "Wasatch Front · Utah" in response.text
    assert 'src="/assets/terrasatch-logo.svg"' in response.text
    assert "terrasatch-logo-BEpaywXF.png" not in response.text
    assert "Developer + Operator Gateways" in response.text
    assert "Field Intelligence Stack" in response.text
    assert "TerraListen" in response.text
    assert "Organizations + Sites" in response.text
    assert "Structured Events" in response.text
    assert "REST + Realtime" in response.text
    assert "terrain-strip" in response.text
    assert "/health/ready" in response.text
    assert "/openapi.json" in response.text
    assert "/admin" in response.text
    assert "/docs" in response.text
    assert "landing-test" in response.text


@pytest.mark.asyncio
async def test_local_brand_asset_is_served_by_api() -> None:
    application = create_app(make_settings())
    transport = httpx.ASGITransport(app=application)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/assets/terrasatch-logo.svg")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg+xml")
    assert "TERRASATCH" in response.text
    assert "TERRAIN INTELLIGENCE" in response.text
    assert "max-age=86400" in response.headers["cache-control"]


@pytest.mark.asyncio
async def test_landing_page_does_not_advertise_disabled_swagger() -> None:
    application = create_app(make_settings(docs_enabled=False))
    transport = httpx.ASGITransport(app=application)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/")

    assert response.status_code == 200
    assert 'href="/docs"' not in response.text
    assert "Swagger Off" in response.text
    assert "Disabled in this environment" in response.text
