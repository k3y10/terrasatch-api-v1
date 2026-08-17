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
async def test_root_serves_provider_aware_satchy_radio_console() -> None:
    application = create_app(make_settings())
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    for expected in (
        "TerraSatch · TerraListen Radio Console",
        "Satchy, the TerraSatch Sasquatch",
        "/assets/terralisten-sasquatch.webp",
        'rel="icon" type="image/png" href="/assets/terralisten-sasquatch.png"',
        "Satchy AI Radio Channel",
        "SATCHY · AI AGENT",
        "TX ORCHESTRATION",
        "PROVIDER-GATED",
        "TX REQUIRES CAPABLE PROVIDER + OPERATOR POLICY",
        "RX ↔ SATCHY ↔ TX",
        "/health/ready",
        "/openapi.json",
        "/api/v1/reference",
        "/admin",
        "/docs",
        "landing-test",
    ):
        assert expected in response.text

    assert "Receive Only" not in response.text
    assert "Receive-only radio intelligence" not in response.text
    assert "https://www.terrasatch.com/terralisten-sasquatch.png" not in response.text


@pytest.mark.asyncio
async def test_landing_is_a_no_document_scroll_viewport_shell() -> None:
    application = create_app(make_settings())
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/")

    assert response.status_code == 200
    assert "html,body{width:100%;height:100%;margin:0;overflow:hidden}" in response.text
    assert "height:100dvh" in response.text
    assert "grid-template-columns:minmax(0,1fr) 325px" in response.text
    assert "@media(max-width:1050px)" in response.text
    assert "@media(max-width:800px)" in response.text
    assert "@media(max-width:600px)" in response.text


@pytest.mark.asyncio
async def test_radio_visual_uses_fluid_bars() -> None:
    application = create_app(make_settings())
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/")

    assert response.status_code == 200
    assert ".bars i{flex:1;" in response.text
    assert "--h:" in response.text


@pytest.mark.asyncio
async def test_local_sasquatch_asset_is_served_by_api() -> None:
    application = create_app(make_settings())
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/assets/terralisten-sasquatch.webp")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/webp")
    assert response.content.startswith(b"RIFF")
    assert b"WEBP" in response.content[:16]
    assert len(response.content) > 10_000
    assert "max-age=86400" in response.headers["cache-control"]


@pytest.mark.asyncio
async def test_local_sasquatch_preview_asset_is_served_by_api() -> None:
    application = create_app(make_settings())
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/assets/terralisten-sasquatch.png")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/png")
    assert response.content.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(response.content) > 8_000
    assert "max-age=86400" in response.headers["cache-control"]


@pytest.mark.asyncio
async def test_local_brand_fallback_asset_is_still_served_by_api() -> None:
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
async def test_landing_page_does_not_link_disabled_swagger() -> None:
    application = create_app(make_settings(docs_enabled=False))
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/")

    assert response.status_code == 200
    assert 'href="/docs"' not in response.text
    assert "Docs Off" in response.text
