from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

import terrasatch.edge.api as edge_api
import terrasatch.edge.service as edge_service
from terrasatch.config import Settings
from terrasatch.edge.schemas import EdgeHeartbeatRequest, PairingStartRequest


@pytest.mark.asyncio
async def test_pairing_url_uses_configured_public_api_base(monkeypatch) -> None:
    settings = Settings(
        environment="production",
        deployment_name="edge-regression-test",
        api_base_url="https://api.terrasatch.com",
        cors_origins=[],
    )
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(settings=settings)),
        base_url="http://internal-proxy/",
    )
    pairing = SimpleNamespace(
        id=uuid4(),
        user_code="ABCD-EFGH",
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )

    async def fake_run_database(_settings, _operation):
        return pairing, "device-code"

    monkeypatch.setattr(edge_api, "_run_database", fake_run_database)

    response = await edge_api.post_pairing(PairingStartRequest(name="Linux Edge"), request)

    assert response.verification_url == (
        "https://api.terrasatch.com/admin/edge/pair?code=ABCD-EFGH"
    )


@pytest.mark.asyncio
async def test_heartbeat_refreshes_device_before_route_serialization(monkeypatch) -> None:
    organization_id = uuid4()
    api_key_id = uuid4()
    device = SimpleNamespace(
        agent_version="0.2.1",
        hardware_inventory=[],
        capabilities=[],
        last_seen_at=None,
    )

    async def fake_get_device_for_api_key(_session, *, organization_id, api_key_id):
        return device

    monkeypatch.setattr(edge_service, "get_device_for_api_key", fake_get_device_for_api_key)

    class FakeSession:
        def __init__(self) -> None:
            self.flushed = False
            self.refreshed = None

        async def flush(self) -> None:
            self.flushed = True

        async def refresh(self, value) -> None:
            self.refreshed = value

    session = FakeSession()
    payload = EdgeHeartbeatRequest(
        agent_version="0.2.2",
        hardware_inventory=[{"name": "k3y10", "platform": "Linux"}],
        capabilities=["edge_runtime", "serial"],
    )

    result = await edge_service.heartbeat_device(
        session,  # type: ignore[arg-type]
        organization_id=organization_id,
        api_key_id=api_key_id,
        payload=payload,
    )

    assert result is device
    assert session.flushed is True
    assert session.refreshed is device
    assert device.agent_version == "0.2.2"
    assert device.hardware_inventory == payload.hardware_inventory
    assert device.capabilities == ["edge_runtime", "serial"]
    assert device.last_seen_at is not None
