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
async def test_root_serves_branded_terrasatch_radio_console() -> None:
    application = create_app(make_settings())
    transport = httpx.ASGITransport(app=application)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "TERRASATCH RADIO CONSOLE" in response.text
    assert "Terrain Intelligence · TerraListen" in response.text
    assert "WASATCH FRONT · UTAH" in response.text
    assert 'src="/assets/terrasatch-logo.svg"' in response.text
    assert "SASSY" in response.text
    assert "TERRALISTEN CORE" in response.text
    assert "RX · CHECKING" in response.text
    assert "MODE: RECEIVE + STRUCTURE" in response.text
    assert "TX: DISABLED" in response.text
    assert "LIVE SYSTEM FEED" in response.text
    assert "RADIO → TRANSCRIPT → TERRAENGINE → EVENT" in response.text
    assert "LISTEN" in response.text
    assert "WATCH" in response.text
    assert "LEARN" in response.text
    assert "ADAPT" in response.text
    assert "/health/ready" in response.text
    assert "/openapi.json" in response.text
    assert "/api/v1/reference" in response.text
    assert "/admin" in response.text
    assert "/docs" in response.text
    assert "landing-test" in response.text


@pytest.mark.asyncio
async def test_landing_is_a_single_viewport_app_shell() -> None:
    application = create_app(make_settings())
    transport = httpx.ASGITransport(app=application)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/")

    assert response.status_code == 200
    assert "height:100dvh" in response.text
    assert "overflow:hidden" in response.text
    assert "grid-template-rows:64px minmax(0,1fr) 36px" in response.text
    assert 'id="revision"' in response.text
    assert 'id="footer-revision"' in response.text


@pytest.mark.asyncio
async def test_local_brand_asset_is_served_by_api() -> None:
    application = create_app(make_settings())
    transport = httpx.ASGITransport(app=application)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/assets/terrasatch-logo.svg")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg+xml")
    assert "TerraSatch Sassy" in response.text
    assert "Sasquatch mascot Sassy" in response.text
    assert "TERRASATCH" in response.text
    assert "SASSY · TERRAIN INTELLIGENCE" in response.text
    assert "max-age=86400" in response.headers["cache-control"]


@pytest.mark.asyncio
async def test_landing_page_does_not_advertise_disabled_swagger() -> None:
    application = create_app(make_settings(docs_enabled=False))
    transport = httpx.ASGITransport(app=application)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/")

    assert response.status_code == 200
    assert 'href="/docs"' not in response.text
    assert "Docs Off" in response.text
    assert "DOCS OFF" in response.text
