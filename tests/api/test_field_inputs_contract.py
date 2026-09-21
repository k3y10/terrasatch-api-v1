"""Public contract checks for Garmin and mobile field inputs."""

from uuid import uuid4

import httpx
import pytest

from terrasatch.config import Settings
from terrasatch.main import create_app


@pytest.mark.asyncio
async def test_openapi_exposes_garmin_and_mobile_field_input_routes() -> None:
    app = create_app(
        Settings(
            environment="local",
            deployment_name="field-input-contract",
            api_base_url="http://testserver",
            intelligence_provider="deterministic",
            admin_session_secret="field-input-session-secret",
        )
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "post" in paths["/api/v1/field/garmin/inreach/{connection_id}"]
    assert "post" in paths[
        "/api/v1/workspace/organizations/{organization_id}/field/observations"
    ]


@pytest.mark.asyncio
async def test_garmin_receiver_requires_static_token_before_connection_lookup() -> None:
    app = create_app(
        Settings(
            environment="local",
            deployment_name="field-input-auth",
            api_base_url="http://testserver",
            intelligence_provider="deterministic",
        )
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            f"/api/v1/field/garmin/inreach/{uuid4()}",
            json={"Version": "4.0", "Events": []},
        )

    assert response.status_code == 401
    payload = response.json()
    assert payload["error"]["code"] == "authentication_failed"
