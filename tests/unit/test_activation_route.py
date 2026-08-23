from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

import pytest

from terrasatch.api import radio
from terrasatch.auth.dependencies import Principal
from terrasatch.config import Settings
from terrasatch.radio.schemas import TransmissionCreateRequest


ORG_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
API_KEY_ID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
SITE_ID = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
TRANSMISSION_ID = UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
TRANSCRIPT_ID = UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")


class FakeSession:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False
        self.flushed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True

    async def flush(self) -> None:
        self.flushed = True


@pytest.mark.asyncio
async def test_activated_route_processes_stripped_copy_but_preserves_source_transcript(monkeypatch) -> None:
    session = FakeSession()
    captured: dict[str, object] = {}
    now = datetime.now(UTC)

    monkeypatch.setattr(radio, "create_session_factory", lambda _settings: lambda: session)

    async def fake_validate(*_args, **_kwargs):
        return SimpleNamespace(
            enforced=True,
            accepted=True,
            intelligence_text="Wind loading observed on the north ridge.",
        )

    async def fake_ingest(_session, *, settings, organization_id, payload):
        captured["settings"] = settings
        captured["organization_id"] = organization_id
        captured["payload"] = payload
        transmission = SimpleNamespace(
            id=TRANSMISSION_ID,
            organization_id=organization_id,
            site_id=payload.site_id,
            agent_id=payload.agent_id,
            channel_id=payload.channel_id,
            source_type=payload.source,
            source_message_id=payload.source_message_id,
            started_at=payload.started_at,
            ended_at=payload.ended_at,
            received_at=now,
            created_at=now,
        )
        transcript = SimpleNamespace(
            id=TRANSCRIPT_ID,
            organization_id=organization_id,
            transmission_id=TRANSMISSION_ID,
            raw_text=payload.text,
            normalized_text=" ".join(payload.text.split()),
            language="en",
            confidence=1.0,
            provider="submitted_text",
            model=None,
            processing_latency_ms=1,
            created_at=now,
        )
        return transmission, transcript, [], False

    async def fake_publish(*_args, **_kwargs):
        return None

    monkeypatch.setattr(radio, "validate_edge_ingest_activation", fake_validate)
    monkeypatch.setattr(radio, "ingest_transmission", fake_ingest)
    monkeypatch.setattr(radio, "publish_event", fake_publish)

    settings = Settings(
        environment="local",
        deployment_name="activation-route-test",
        intelligence_provider="deterministic",
    )
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(settings=settings)))
    principal = Principal(
        organization_id=ORG_ID,
        api_key_id=API_KEY_ID,
        scopes=frozenset({"edge:ingest"}),
    )
    payload = TransmissionCreateRequest(
        site_id=SITE_ID,
        text="Field Team to TerraSatch. Wind loading observed on the north ridge.",
        source="terrasatch-edge-stt",
        source_message_id="activation-route-source",
    )

    response = await radio.post_transmission(payload, request, principal)

    processed_payload = captured["payload"]
    assert isinstance(processed_payload, TransmissionCreateRequest)
    assert processed_payload.text == "Wind loading observed on the north ridge."
    assert response.transcript.raw_text == payload.text
    assert response.transcript.normalized_text == payload.text
    assert session.flushed is True
    assert session.committed is True
    assert session.rolled_back is False
