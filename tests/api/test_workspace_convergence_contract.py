"""Contract tests for organization workspace convergence state."""

from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest

from terrasatch.config import Settings
from terrasatch.main import create_app
from terrasatch.workspace.convergence import (
    build_capability_manifest,
    workspace_profile_payload,
)


def test_default_workspace_profile_is_legacy_and_discovery_safe() -> None:
    payload = workspace_profile_payload(None)

    assert payload["runtime_mode"] == "legacy"
    assert payload["operational_domain"] == "general"
    assert payload["workspace_template"] == "general"
    assert payload["discovery_state"] == {"status": "not_started"}


def test_capability_manifest_only_exposes_runtime_ready_connections_and_edge_caps() -> None:
    catalog = [
        {
            "key": "nws_forecast",
            "connected": True,
            "runtime_ready": True,
            "capability_details": [
                {
                    "key": "weather.forecast.read",
                    "label": "Read weather forecasts",
                    "access": "read",
                }
            ],
        },
        {
            "key": "slack",
            "connected": False,
            "runtime_ready": True,
            "capability_details": [
                {
                    "key": "notification.send",
                    "label": "Send notifications",
                    "access": "write",
                }
            ],
        },
    ]
    edge = SimpleNamespace(
        id=uuid4(),
        site_id=uuid4(),
        name="Field Edge",
        agent_version="0.2.8",
        capabilities=["radio:receive", "radio:transmit"],
        last_seen_at=None,
        enabled=True,
    )

    manifest = build_capability_manifest(
        profile=None,
        catalog=catalog,
        devices=[edge],
    )

    assert manifest["runtime_mode"] == "legacy"
    assert manifest["read"] == ["weather.forecast.read"]
    assert manifest["write"] == []
    assert manifest["edge"] == ["radio:receive", "radio:transmit"]
    assert manifest["physical"] == ["radio:transmit"]
    assert manifest["connected_providers"] == ["nws_forecast"]
    assert manifest["policy"] == {
        "agent_reads_enabled": False,
        "agent_proposals_enabled": False,
        "shadow_only": False,
        "consequential_actions_require_approval": True,
        "physical_actions_require_approval": True,
    }


@pytest.mark.asyncio
async def test_openapi_exposes_workspace_convergence_contract() -> None:
    app = create_app(
        Settings(
            environment="local",
            deployment_name="workspace-convergence-contract",
            api_base_url="http://testserver",
            intelligence_provider="deterministic",
            admin_session_secret="workspace-convergence-session-secret",
        )
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/openapi.json")

    assert response.status_code == 200
    path = response.json()["paths"][
        "/api/v1/workspace/organizations/{organization_id}/convergence"
    ]
    assert "get" in path
    assert "patch" in path
