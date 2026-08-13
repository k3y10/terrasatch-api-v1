import pytest

from terrasatch.intelligence.core import EventType, TerraEngine


@pytest.mark.asyncio
async def test_terraengine_extracts_supported_field_observation_fields() -> None:
    events = await TerraEngine().process(
        text="Patrol 4 reports a field observation on the east-facing rollover around 9,800 feet.",
    )

    assert len(events) == 1
    event = events[0]
    assert event.callsign == "Patrol 4"
    assert event.aspect == "E"
    assert event.elevation_ft == 9800
    assert event.confidence >= 0.6


@pytest.mark.asyncio
async def test_terraengine_does_not_fabricate_missing_location_fields() -> None:
    events = await TerraEngine().process(text="Dispatch copy.", callsign_hint="Dispatch")

    assert len(events) == 1
    event = events[0]
    assert event.event_type == EventType.GENERAL_UPDATE
    assert event.callsign == "Dispatch"
    assert event.location_text is None
    assert event.aspect is None
    assert event.elevation_ft is None
    assert event.latitude is None
    assert event.longitude is None


@pytest.mark.asyncio
async def test_terraengine_understands_worded_demo_elevation() -> None:
    events = await TerraEngine().process(
        text="East facing, roughly ninety-eight hundred feet.",
        callsign_hint="Patrol 4",
    )

    assert events[0].aspect == "E"
    assert events[0].elevation_ft == 9800
