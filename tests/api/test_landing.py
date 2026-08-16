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
async def test_root_serves_clean_terralisten_operations_console() -> None:
    application = create_app(make_settings())
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    for expected in (
        "TerraSatch · TerraListen Radio Console",
        "TerraSatch Sasquatch",
        "/assets/terralisten-sasquatch.webp",
        'rel="icon" type="image/png" href="/assets/terralisten-sasquatch.png"',
        (
            'property="og:image" content="'
            "https://api.terrasatch.com/assets/terralisten-sasquatch.png\""
        ),
        'name="twitter:card" content="summary"',
        "TERRALISTEN",
        "TerraListen Receiver",
        "Receive-only radio intelligence for field operations.",
        "Waiting for field receiver input",
        "LIVE INTELLIGENCE",
        "SYSTEM STATUS",
        "RECEIVER STATUS",
        "SYSTEM INFO",
        "LISTEN</b> · WATCH · LEARN · ADAPT",
        "/health/ready",
        "/openapi.json",
        "/api/v1/reference",
        "/api/v1/transmissions",
        "/ws/v1/events",
        "/admin",
        "/docs",
        "landing-test",
    ):
        assert expected in response.text

    assert "https://www.terrasatch.com/terralisten-sasquatch.png" not in response.text
    assert "API · RX" not in response.text
    assert "FIELD INTELLIGENCE RECEIVER" not in response.text


@pytest.mark.asyncio
async def test_landing_is_a_no_document_scroll_viewport_shell() -> None:
    application = create_app(make_settings())
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/")

    assert response.status_code == 200
    assert "html,body{width:100%;height:100%;margin:0;overflow:hidden}" in response.text
    assert "height:100dvh" in response.text
    assert "grid-template-rows:76px minmax(0,1fr) 36px" in response.text
    assert "grid-template-columns:minmax(0,1fr) minmax(280px,330px)" in response.text
    assert "@media(max-width:1100px)" in response.text
    assert "@media(max-width:820px)" in response.text
    assert "@media(max-width:640px)" in response.text
    assert "@media(max-height:700px)" in response.text


@pytest.mark.asyncio
async def test_receiver_waveform_uses_fluid_bar_sizing() -> None:
    application = create_app(make_settings())
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/")

    assert response.status_code == 200
    assert "gap:clamp(1px,.18vw,3px)" in response.text
    assert "flex:1 1 0;width:auto;min-width:0" in response.text
    assert "transform-origin:50% 100%" in response.text
    assert ".wave i{width:4px;min-width:4px" not in response.text
    assert ".wave i{width:3px;min-width:3px" not in response.text


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
