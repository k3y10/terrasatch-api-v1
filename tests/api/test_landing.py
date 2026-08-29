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


async def _get(path: str = "/", *, docs_enabled: bool = True) -> httpx.Response:
    app = create_app(make_settings(docs_enabled=docs_enabled))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.get(path)


@pytest.mark.asyncio
async def test_root_serves_provider_aware_satchy_radio_console() -> None:
    response = await _get()
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    for expected in (
        "TerraSatch · TerraListen Radio Console",
        'aria-label="TerraSatch field intelligence"',
        '<span class="brand-wordmark"><img src="/assets/terrasatch.png"',
        "Satchy, the TerraSatch Sasquatch",
        'rel="icon" type="image/png" href="/assets/satchy.png"',
        "Satchy AI Radio Channel",
        "SATCHY · AI AGENT",
        "TERRASATCH NETWORK",
        "REGISTERED NODES",
        "FIELD SITES",
        "NETWORK HEALTH",
        "/api/v1/network/status",
        "/portal",
        "/admin",
        "landing-test",
    ):
        assert expected in response.text
    assert "https://www.terrasatch.com/terralisten-sasquatch.png" not in response.text
    assert ">TERRASATCH</strong><b>TERRALISTEN<" not in response.text


@pytest.mark.asyncio
async def test_landing_is_a_no_document_scroll_viewport_shell() -> None:
    response = await _get()
    assert response.status_code == 200
    assert "html,body{width:100%;height:100%;margin:0;overflow:hidden}" in response.text
    assert "height:100dvh" in response.text
    assert "@media(max-width:820px)" in response.text
    assert "@media(max-width:600px)" in response.text


@pytest.mark.asyncio
async def test_radio_visual_animates_standby_heartbeat_and_fluid_bars() -> None:
    response = await _get()
    assert response.status_code == 200
    assert "@keyframes listenPulse" in response.text
    assert "@keyframes heartbeat" in response.text
    assert 'id="radio-signal" data-edge="standby"' in response.text
    assert "setInterval(updateHealth,15000)" in response.text
    assert "setInterval(refreshNetwork,30000)" in response.text
    assert "setInterval(refreshFleet,10000)" in response.text


@pytest.mark.asyncio
async def test_health_states_have_distinct_non_brand_colors() -> None:
    response = await _get()
    assert response.status_code == 200
    assert "--green:#6ee7a0" in response.text
    assert "--yellow:#f6c65b" in response.text
    assert "--red:#ff6b6b" in response.text


@pytest.mark.asyncio
async def test_local_sasquatch_asset_is_served_by_api() -> None:
    response = await _get("/assets/terralisten-sasquatch.webp")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/webp")
    assert response.content.startswith(b"RIFF")
    assert b"WEBP" in response.content[:16]
    assert len(response.content) > 10_000
    assert "max-age=86400" in response.headers["cache-control"]


@pytest.mark.asyncio
async def test_local_sasquatch_preview_asset_is_served_by_api() -> None:
    response = await _get("/assets/terralisten-sasquatch.png")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/png")
    assert response.content.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(response.content) > 8_000
    assert "max-age=86400" in response.headers["cache-control"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("asset_url", "maximum_size"),
    [
        ("/assets/terrasatch.png", 900_000),
        ("/assets/satchy.png", 1_300_000),
    ],
)
async def test_current_brand_assets_are_served_within_budget(
    asset_url: str,
    maximum_size: int,
) -> None:
    response = await _get(asset_url)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/png")
    assert response.content.startswith(b"\x89PNG\r\n\x1a\n")
    assert 1_000 < len(response.content) <= maximum_size
    assert "max-age=86400" in response.headers["cache-control"]


@pytest.mark.asyncio
async def test_local_brand_fallback_asset_is_still_served_by_api() -> None:
    response = await _get("/assets/terrasatch-logo.svg")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg+xml")
    assert "TERRASATCH" in response.text
    assert "max-age=86400" in response.headers["cache-control"]


@pytest.mark.asyncio
async def test_landing_page_does_not_link_disabled_swagger() -> None:
    response = await _get(docs_enabled=False)
    assert response.status_code == 200
    assert 'href="/docs"' not in response.text
    assert "Docs Off" in response.text
