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


@pytest.mark.asyncio
async def test_field_observation_preserves_negated_avalanche_and_demo_context() -> None:
    events = await TerraEngine().process(
        text=(
            "Field observation. Cardiff Bowl, northeast-facing aspect. "
            "No avalanches observed. Sunny clear weather. Everything is green."
        ),
    )

    assert len(events) == 1
    event = events[0]
    assert event.event_type == EventType.OBSERVATION
    assert event.location_text == "Cardiff Bowl"
    assert event.aspect == "NE"
    assert event.severity is None
    assert event.summary == "No avalanche activity observed."
    assert event.data["negative_findings"] == ["avalanche"]
    assert event.data["observation"] == "No avalanche observed"
    assert event.data["avalanche_problem"] == "None observed"
    assert event.data["weather_conditions"] == ["sunny", "clear"]
    assert event.data["field_status"] == "green"
    assert "avalanche" not in event.data.get("keywords", [])


@pytest.mark.asyncio
async def test_positive_avalanche_report_remains_avalanche_event() -> None:
    events = await TerraEngine().process(
        text="Field observation. Cardiff Bowl. Avalanche observed on the northeast aspect.",
    )

    event = events[0]
    assert event.event_type == EventType.AVALANCHE
    assert event.severity == "moderate"
    assert event.location_text == "Cardiff Bowl"
    assert event.aspect == "NE"
    assert "avalanche" in event.data["keywords"]


@pytest.mark.asyncio
async def test_negated_avalanche_does_not_hide_positive_instability_signal() -> None:
    events = await TerraEngine().process(
        text="No avalanches observed at Cardiff Bowl, but shooting cracks on the northeast aspect.",
    )

    event = events[0]
    assert event.event_type == EventType.OBSERVATION
    assert event.summary == "Shooting cracks reported."
    assert event.severity == "moderate"
    assert event.data["negative_findings"] == ["avalanche"]
    assert "shooting cracks" in event.data["keywords"]
    assert "avalanche" not in event.data["keywords"]
