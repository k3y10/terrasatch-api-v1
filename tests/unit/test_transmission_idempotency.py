from types import SimpleNamespace
from uuid import uuid4

import pytest

from terrasatch.config import Settings
from terrasatch.radio.schemas import TransmissionCreateRequest
from terrasatch.radio.service import ingest_transmission


class FakeSession:
    def __init__(self, transmission, transcript, events):
        self.scalar_results = [transmission, transcript]
        self.events = events

    async def scalar(self, _statement):
        return self.scalar_results.pop(0)

    async def scalars(self, _statement):
        return self.events


@pytest.mark.asyncio
async def test_source_message_retry_returns_existing_records_without_duplicate_event() -> None:
    organization_id = uuid4()
    site_id = uuid4()
    transmission = SimpleNamespace(id=uuid4(), source_message_id="stable-edge-source")
    transcript = SimpleNamespace(id=uuid4(), transmission_id=transmission.id)
    event = SimpleNamespace(id=uuid4(), transmission_id=transmission.id)
    session = FakeSession(transmission, transcript, [event])

    result = await ingest_transmission(
        session,
        settings=Settings(environment="local", intelligence_provider="deterministic"),
        organization_id=organization_id,
        payload=TransmissionCreateRequest(
            site_id=site_id,
            text="Retry of a previously accepted field transmission.",
            source="terrasatch-edge-radio-bca-ch05",
            source_message_id="stable-edge-source",
        ),
    )

    existing_transmission, existing_transcript, events, duplicate = result
    assert duplicate is True
    assert existing_transmission is transmission
    assert existing_transcript is transcript
    assert events == [event]
