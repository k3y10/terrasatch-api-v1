from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from terrasatch.intelligence.core import EventType, TerraEngine
from terrasatch.radio.schemas import TransmissionCreateRequest

UAC_SITE = UUID("11111111-1111-1111-1111-111111111111")
COLORADO_SITE = UUID("22222222-2222-2222-2222-222222222222")
PYRO_SITE = UUID("33333333-3333-3333-3333-333333333333")


def _fixture(site_id: UUID, source_id: str, text: str) -> TransmissionCreateRequest:
    started = datetime(2026, 8, 28, 18, 0, tzinfo=UTC)
    return TransmissionCreateRequest(
        site_id=site_id,
        text=text,
        source="terrasatch-edge-radio-bca-ch05",
        source_message_id=source_id,
        started_at=started,
        ended_at=started + timedelta(seconds=6.25),
        transcript_provider="faster_whisper",
        transcript_model="base.en",
        rf_metadata={
            "receiver_device_id": "terralisten-fixture-01",
            "radio_profile": "bca-frs-na",
            "channel": 5,
            "frequency_hz": 462_662_500,
            "duration_ms": 6250,
            "tone_detected": False,
        },
    )


def test_uac_and_colorado_fixtures_keep_distinct_tenant_site_targets() -> None:
    uac = _fixture(
        UAC_SITE,
        "uac-radio-fixture-1",
        "UAC to TerraSatch. Patrol Four reporting from Cardiff Bowl. Recent wind "
        "loading on the northeast aspect with a small skier-triggered slab observed.",
    )
    colorado = _fixture(
        COLORADO_SITE,
        "caic-radio-fixture-1",
        "CAIC field team reporting from Berthoud Pass. Shooting cracks and active snow "
        "transport observed near Current Creek.",
    )
    assert uac.site_id == UAC_SITE
    assert colorado.site_id == COLORADO_SITE
    assert uac.site_id != colorado.site_id
    assert uac.source_message_id != colorado.source_message_id
    assert uac.rf_metadata.channel == colorado.rf_metadata.channel == 5


def test_generic_pyro_fixture_uses_same_transmission_contract() -> None:
    pyro = _fixture(
        PYRO_SITE,
        "pyro-radio-fixture-1",
        "Division Alpha to command. Winds have shifted southwest near the north drainage. "
        "Spot fire approximately fifty yards beyond the previous line.",
    )
    assert pyro.site_id == PYRO_SITE
    assert pyro.source == "terrasatch-edge-radio-bca-ch05"
    assert pyro.rf_metadata.duration_ms == 6250
    assert "avalanche" not in pyro.text.lower()


@pytest.mark.asyncio
async def test_uac_and_colorado_demo_text_still_creates_located_operational_events() -> None:
    uac = await TerraEngine().process(
        text=(
            "UAC to TerraSatch. Patrol Four reporting from Cardiff Bowl. Recent wind loading "
            "on the northeast aspect with a small skier-triggered avalanche observed."
        )
    )
    colorado = await TerraEngine().process(
        text=(
            "CAIC field team reporting. Shooting cracks observed near Current Creek "
            "on the northeast aspect."
        )
    )
    assert uac and uac[0].event_type == EventType.AVALANCHE
    assert uac[0].location_text == "Cardiff Bowl"
    assert colorado and colorado[0].event_type == EventType.OBSERVATION
    assert colorado[0].location_text == "Current Creek"


@pytest.mark.asyncio
async def test_pyro_demo_text_is_interpreted_downstream_not_by_receiver_contract() -> None:
    events = await TerraEngine().process(
        text=(
            "Division Alpha to command. Winds have shifted southwest near the north drainage. "
            "Spot fire approximately fifty yards beyond the previous line."
        )
    )
    assert events and events[0].event_type == EventType.FIRE
