from uuid import uuid4

import pytest
from sqlalchemy import select
from test_satchy_control_plane import _seed_session

from terrasatch.actions.models import SatchyAction
from terrasatch.config import Settings
from terrasatch.radio.addressing import CallsignCandidate, parse_radio_addressing
from terrasatch.radio.models import Callsign, RadioConversation
from terrasatch.radio.schemas import TransmissionCreateRequest
from terrasatch.radio.service import ingest_transmission


@pytest.mark.parametrize(
    "text,speaker,recipient",
    [
        ("Base, Field, radio check.", "Field", "Base"),
        ("Field to Base, radio check.", "Field", "Base"),
        ("Base to Field, copy.", "Base", "Field"),
        ("Field calling Base.", "Field", "Base"),
        ("Base, this is Field.", "Field", "Base"),
        ("Base, this is Field. Continuing uphill.", "Field", "Base"),
        ("Base from Field.", "Field", "Base"),
        ("Field for Base.", "Field", "Base"),
        ("Field calling Satchy.", "Field", "Satchy"),
        ("Satchy, Field, status update.", "Field", "Satchy"),
        ("Control Two to Satchy.", "Control 2", "Satchy"),
        (" control   TWO to TERRASATCH.", "Control 2", "Satchy"),
        ("Satchy, Field 2. Observation at Cardiff Bowl.", "Field 2", "Satchy"),
    ],
)
def test_natural_patterns(text, speaker, recipient):
    candidates = [
        CallsignCandidate(uuid4(), name, aliases)
        for name, aliases in [
            ("Base", ()),
            ("Field", ()),
            ("Field 2", ()),
            ("Control 2", ("Control Two",)),
            ("Satchy", ("TerraSatch",)),
        ]
    ]
    result = parse_radio_addressing(text, callsigns=candidates)
    assert (result.speaker_text, result.recipient_text) == (speaker, recipient)
    assert result.addressed_to_agent == (recipient == "Satchy")


@pytest.mark.parametrize(
    "text",
    [
        "Field observation at Cardiff Bowl, 9,800 feet.",
        "Field to Basecamp, copy.",
        "Somebody calling Base.",
        "We heard Field calling Satchy.",
        "Field for Base operations today.",
    ],
)
def test_prose_is_not_addressing(text):
    result = parse_radio_addressing(
        text, callsigns=[CallsignCandidate(uuid4(), "Field"), CallsignCandidate(uuid4(), "Base")]
    )
    assert result.speaker_text is None
    assert result.recipient_text is None
    assert not result.addressed_to_agent


async def ingest(session, seed, text, **kwargs):
    return await ingest_transmission(
        session,
        settings=Settings(intelligence_provider="deterministic"),
        organization_id=seed["organization"].id,
        payload=TransmissionCreateRequest(
            site_id=seed["site"].id,
            agent_id=seed["agent"].id,
            channel_id=seed["channel"].id,
            text=text,
            source="test",
            source_message_id=str(uuid4()),
            **kwargs,
        ),
    )


async def test_conversation_patterns_and_standalone_capture():
    engine, session, seed = await _seed_session()
    try:
        for name in ["Base", "Field"]:
            session.add(
                Callsign(
                    organization_id=seed["organization"].id,
                    site_id=seed["site"].id,
                    name=name,
                    aliases=[],
                    enabled=True,
                )
            )
        await session.flush()
        ids = []
        for text in [
            "Base, Field, radio check one.",
            "Field to Base, radio check two.",
            "Base to Field, copy.",
            "Base, this is Field. Continuing uphill.",
        ]:
            tx, _, _, _ = await ingest(session, seed, text)
            ids.append(tx.conversation_id)
        assert len(set(ids)) == 1
        conversation = await session.get(RadioConversation, ids[0])
        assert conversation.participants == ["Base", "Field"]
        assert conversation.participant_fingerprint == "base|field"
        first, _, _, _ = await ingest(session, seed, "Field calling Satchy.")
        second, _, _, _ = await ingest(session, seed, "Satchy, Field.")
        assert first.conversation_id == second.conversation_id
        assert first.addressed_to_agent and second.addressed_to_agent
        tx, transcript, events, _ = await ingest(
            session,
            seed,
            "Field observation at Cardiff Bowl, 9,800 feet. Northwest aspect. "
            "Moderate wind. No avalanche observed.",
        )
        assert transcript.transmission_id == tx.id
        assert events and events[0].event_type == "OBSERVATION"
        assert events[0].location_text == "Cardiff Bowl"
        assert events[0].elevation_ft == 9800
        assert events[0].aspect == "NW"
        assert events[0].confidence > 0
        assert tx.recipient_text is None
        assert not tx.addressed_to_agent
        assert (
            await session.scalar(
                select(SatchyAction).where(SatchyAction.source_transmission_id == tx.id)
            )
            is None
        )
    finally:
        await session.close()
        await engine.dispose()
