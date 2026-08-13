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
async def test_terraengine_does_not_treat_callsign_number_as_elevation() -> None:
    events = await TerraEngine().process(
        text="Dispatch, Patrol 4. Wind loading is visible near the ridgeline.",
    )

    assert len(events) == 1
    assert events[0].callsign == "Patrol 4"
    assert events[0].elevation_ft is None


@pytest.mark.asyncio
async def test_short_numeric_elevation_requires_explicit_units() -> None:
    without_units = await TerraEngine().process(
        text="Unit 12 heading toward the staging area.",
    )
    with_units = await TerraEngine().process(
        text="Unit 12 reports water crossing the trail at 85 ft.",
    )

    assert without_units[0].elevation_ft is None
    assert with_units[0].elevation_ft == 85


@pytest.mark.asyncio
async def test_terraengine_accepts_common_bare_four_digit_elevation() -> None:
    events = await TerraEngine().process(
        text="Patrol 4 reports wind loading on the east aspect around 9800.",
    )

    assert events[0].elevation_ft == 9800


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
