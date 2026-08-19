from pathlib import Path

import httpx
import pytest

import terrasatch.main as main_module
from terrasatch.config import Settings


CSV = """Date,Region,Place,Trigger,Trigger: additional info,Weak Layer,Depth,Width,Vertical,Aspect,Elevation,Coordinates,Caught,Carried,Buried - Partly,Buried - Fully,Injured,Killed,Accident and Rescue Summary,Terrain Summary,Weather Conditions and History,Comments 1,Comments 2,Comments 3,Comments 4,Comment
05/31/2026,Salt Lake,Kessler Peak,Natural,,Ground interface,,,100',N,10000',40.6311,-111.6808,,,,,,,Warm afternoon,North-facing terrain,Recent warming,,,,
04/28/2026,Salt Lake,Monitors,Snowboarder,Triggered by rider,Wet grains,10\",50',,E,9800',40.6351,-111.5758,1,1,,,,,Rider carried short distance,Steep east-facing terrain,Wet snow cycle,Observed wet loose activity,,,,
03/01/2026,Provo,Aspen Grove,Natural,,Facets,2',200',500',NE,9000',40.3000,-111.6000,,,,,,,Large natural,Upper elevation terrain,Storm slab cycle,,,,
"""


def make_settings(path: str | None = None) -> Settings:
    return Settings(
        environment="local",
        deployment_name="uac-archive-test",
        api_base_url="http://testserver",
        cors_origins=[],
        uac_archive_path=path,
    )


@pytest.mark.asyncio
async def test_uac_archive_requires_configured_file() -> None:
    application = main_module.create_app(make_settings())
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/v1/uac/archive")

    assert response.status_code == 503
    assert "TERRASATCH_UAC_ARCHIVE_PATH" in response.json()["detail"]


@pytest.mark.asyncio
async def test_uac_archive_filters_and_returns_source_context(tmp_path: Path) -> None:
    path = tmp_path / "avalanches.csv"
    path.write_text(CSV, encoding="utf-8")
    application = main_module.create_app(make_settings(str(path)))
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            "/api/v1/uac/archive",
            params={"region": "salt-lake", "trigger": "human", "mapped": "0", "limit": 10},
        )

    assert response.status_code == 200
    assert "public" in response.headers["cache-control"]
    payload = response.json()
    assert payload["metadata"]["dataMode"] == "terrasatch-oci-archive"
    assert payload["metadata"]["archiveTotal"] == 3
    assert payload["metadata"]["matchedRecords"] == 1
    assert payload["records"][0]["location"] == "Monitors"
    assert payload["records"][0]["trigger"] == "Snowboarder"
    assert payload["records"][0]["depth"] == "10 in"
    assert payload["records"][0]["width"] == "50 ft"
    assert payload["records"][0]["archiveContext"]["caught"] == 1
    assert payload["records"][0]["archiveContext"]["carried"] == 1


@pytest.mark.asyncio
async def test_uac_archive_date_search_and_region_filters(tmp_path: Path) -> None:
    path = tmp_path / "avalanches.csv"
    path.write_text(CSV, encoding="utf-8")
    application = main_module.create_app(make_settings(str(path)))
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            "/api/v1/uac/archive",
            params={
                "region": "salt-lake",
                "q": "ground interface",
                "from": "2026-05-01",
                "to": "2026-05-31",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["metadata"]["matchedRecords"] == 1
    assert payload["records"][0]["location"] == "Kessler Peak"


@pytest.mark.asyncio
async def test_openapi_exposes_uac_archive() -> None:
    application = main_module.create_app(make_settings())
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/openapi.json")

    assert response.status_code == 200
    assert "get" in response.json()["paths"]["/api/v1/uac/archive"]
