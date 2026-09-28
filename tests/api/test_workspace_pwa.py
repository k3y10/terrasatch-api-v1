import httpx
import pytest

from terrasatch.config import Settings
from terrasatch.main import create_app


@pytest.mark.asyncio
async def test_workspace_pwa_routes_and_brand_assets():
    app = create_app(Settings(environment="local"))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.get("/portal/manifest.webmanifest")
        assert response.status_code == 200
        manifest = response.json()
        assert manifest["start_url"] == "/portal"
        assert manifest["display"] == "standalone"
        for icon in manifest["icons"]:
            asset = await client.get(icon["src"])
            assert asset.status_code == 200
            assert "image/" in asset.headers["content-type"]
        for asset in ["slack.png", "microsoft-icon.svg", "microsoft-teams.svg", "google-drive.svg"]:
            assert (await client.get("/assets/workspace/integrations/" + asset)).status_code == 200
        offline = await client.get("/portal/offline")
        assert offline.status_code == 200
        assert "not stored for offline access" in offline.text
        worker = await client.get("/portal/service-worker.js")
        assert worker.headers["service-worker-allowed"] == "/portal"
        assert worker.headers["cache-control"] == "no-cache"
        assert "const PUBLIC=['/portal/offline','/assets/workspace/icon.svg']" in worker.text
        assert "cache.put" not in worker.text
        assert "e.request.method!=='GET'" in worker.text
        assert "fetch(e.request).catch" in worker.text
