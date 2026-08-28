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
        'aria-label="TerraSatch field intelligence"',
        '<span class="brand-wordmark"><img src="/assets/terrasatch.png"',
        "Satchy, the TerraSatch Sasquatch",
        "/assets/terrasatch.png",
        'rel="icon" type="image/png" href="/assets/satchy.png"',
        "Satchy AI Radio Channel",
        "SATCHY · AI AGENT",
        "TX ORCHESTRATION",
        "PROVIDER-GATED",
        "TX REQUIRES CAPABLE PROVIDER + OPERATOR POLICY",
        "RX ↔ SATCHY ↔ TX",
        "LISTENING · WAITING FOR EDGE",
        "TERRASATCH NETWORK",
        "REGISTERED NODES",
        "FIELD SITES",
        "MEMBERS",
        "NETWORK HEALTH",
        "PRIVATE FLEET DETAIL",
        "CURRENT COMPATIBILITY",
        "RTL-SDR / Nooelec",
        "HackRF",
        "/api/v1/network/status",
        "/admin/fleet-status",
        "/portal/fleet-status",
        "/portal",
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
    assert ">TERRASATCH</strong><b>TERRALISTEN<" not in response.text
    assert '<span class="brand-name">' not in response.text
    assert ".brand small{display:none}" not in response.text
    assert ".brand-wordmark{display:block;width:210px;height:62px" in response.text
    assert ".brand-wordmark img{display:block;width:210px;height:auto" in response.text


@pytest.mark.asyncio
async def test_landing_is_a_no_document_scroll_viewport_shell() -> None:
    application = create_app(make_settings())
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/")

    assert response.status_code == 200
    assert "html,body{width:100%;height:100%;margin:0;overflow:hidden}" in response.text
    assert "height:100dvh" in response.text
    assert "grid-template-columns:minmax(0,1fr) 340px" in response.text
    assert "@media(max-width:1100px)" in response.text
    assert "@media(max-width:820px)" in response.text
    assert "@media(max-width:600px)" in response.text


@pytest.mark.asyncio
async def test_radio_visual_animates_standby_heartbeat_and_fluid_bars() -> None:
    application = create_app(make_settings())
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/")

    assert response.status_code == 200
    assert ".bars i{flex:1;" in response.text
    assert "--h:" in response.text
    assert "--d:" in response.text
    assert "@keyframes listenPulse" in response.text
    assert "@keyframes heartbeat" in response.text
    assert 'id="radio-signal" data-edge="standby"' in response.text
    assert "setInterval(updateHealth,15000)" in response.text
    assert "setInterval(refreshNetwork,30000)" in response.text
    assert "setInterval(refreshFleet,10000)" in response.text
    assert "setInterval(updateFleet,10000)" not in response.text


@pytest.mark.asyncio
async def test_health_states_have_distinct_non_brand_colors() -> None:
    application = create_app(make_settings())
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/")

    assert response.status_code == 200
    assert "--green:#6ee7a0" in response.text
    assert "--yellow:#f6c65b" in response.text
    assert "--red:#ff6b6b" in response.text
    assert ".health.healthy,.health.online{color:var(--green)}" in response.text
    assert ".health.degraded,.health.stale{color:var(--yellow)}" in response.text
    assert ".health.unhealthy,.health.offline{color:var(--red)}" in response.text


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
@pytest.mark.parametrize(
    ("asset_url", "minimum_size"),
    [
        ("/assets/terrasatch.png", 500_000),
        ("/assets/satchy.png", 1_000_000),
    ],
)
async def test_current_brand_assets_are_served_by_api(asset_url: str, minimum_size: int) -> None:
    application = create_app(make_settings())
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(asset_url)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/png")
    assert response.content.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(response.content) > minimum_size
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
