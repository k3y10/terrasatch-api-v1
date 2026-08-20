import pytest

from terrasatch.config import Settings
from terrasatch.integrations.flaik import FlaikClient, FlaikMode, correlate_radio_text
from terrasatch.intelligence.core import TerraEngine


@pytest.mark.asyncio
async def test_fixture_snapshot_is_pii_minimized_and_operational() -> None:
    snapshot = await FlaikClient(Settings(flaik_mode="fixture")).snapshot()

    assert snapshot.mode == FlaikMode.FIXTURE
    assert snapshot.connected is True
    assert snapshot.source_site == "snowbird.flaik.com"
    assert snapshot.groups_out == 8
    assert snapshot.instructors_active == 12
    assert snapshot.groups
    serialized = snapshot.model_dump_json().casefold()
    for sensitive_field in ("email", "phone", "payroll", "dateofbirth", "address"):
        assert sensitive_field not in serialized


@pytest.mark.asyncio
async def test_radio_text_correlates_to_fixture_group() -> None:
    snapshot = await FlaikClient(Settings(flaik_mode="fixture")).snapshot()
    context = correlate_radio_text(
        "Mountain School 4 checking in from Creekside with the group.",
        snapshot,
    )

    assert context.connected is True
    assert context.group_id == "MS-204"
    assert context.group_label == "Mountain School 4"
    assert context.meeting_area == "Creekside"
    assert context.confidence >= 0.9


@pytest.mark.asyncio
async def test_terraengine_can_attach_flaik_operational_context() -> None:
    events = await TerraEngine().process(
        text="Mountain School 4 heading toward Creekside.",
        operational_context={
            "flaik": {
                "group_id": "MS-204",
                "participant_count": 5,
                "status": "on_mountain",
            }
        },
    )

    assert len(events) == 1
    context = events[0].data["operational_context"]
    assert isinstance(context, dict)
    flaik = context["flaik"]
    assert isinstance(flaik, dict)
    assert flaik["group_id"] == "MS-204"


@pytest.mark.asyncio
async def test_disabled_flaik_mode_never_requires_credentials() -> None:
    snapshot = await FlaikClient(Settings(flaik_mode="disabled")).snapshot()

    assert snapshot.connected is False
    assert snapshot.groups == []
