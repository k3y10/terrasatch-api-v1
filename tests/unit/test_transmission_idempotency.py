from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

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


class FakeNestedTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class ConcurrentRetrySession:
    def __init__(self, *, site, transmission, transcript, events):
        self.scalar_results = [None, site, transmission, transcript]
        self.events = events
        self.added = []
        self.flush_calls = 0

    async def scalar(self, _statement):
        return self.scalar_results.pop(0)

    async def scalars(self, _statement):
        return self.events

    def add(self, value):
        self.added.append(value)

    def begin_nested(self):
        return FakeNestedTransaction()

    async def flush(self):
        self.flush_calls += 1
        if self.flush_calls == 1:
            raise IntegrityError(
                "INSERT INTO transmissions ...",
                {},
                RuntimeError("duplicate source_message_id"),
            )


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


@pytest.mark.asyncio
async def test_concurrent_source_message_retry_returns_winning_records() -> None:
    organization_id = uuid4()
    site_id = uuid4()
    transmission = SimpleNamespace(id=uuid4(), source_message_id="concurrent-edge-source")
    transcript = SimpleNamespace(id=uuid4(), transmission_id=transmission.id)
    event = SimpleNamespace(id=uuid4(), transmission_id=transmission.id)
    site = SimpleNamespace(id=site_id)
    session = ConcurrentRetrySession(
        site=site,
        transmission=transmission,
        transcript=transcript,
        events=[event],
    )

    result = await ingest_transmission(
        session,  # type: ignore[arg-type]
        settings=Settings(environment="local", intelligence_provider="deterministic"),
        organization_id=organization_id,
        payload=TransmissionCreateRequest(
            site_id=site_id,
            text="Concurrent retry of a field transmission.",
            source="terrasatch-edge-radio-bca-ch05",
            source_message_id="concurrent-edge-source",
        ),
    )

    existing_transmission, existing_transcript, events, duplicate = result
    assert duplicate is True
    assert existing_transmission is transmission
    assert existing_transcript is transcript
    assert events == [event]
    assert session.flush_calls == 1
    assert len(session.added) == 1
