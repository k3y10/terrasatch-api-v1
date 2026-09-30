from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from test_satchy_control_plane import _ingest, _seed_session

from terrasatch.actions.models import ActionStatus, ActionType
from terrasatch.actions.service import approve_and_queue_action
from terrasatch.edge.command_service import (
    acknowledge_command,
    complete_command,
    list_device_commands,
)
from terrasatch.edge.models import EdgeCommand, EdgeDevice
from terrasatch.errors import InvalidConfiguration
from terrasatch.identity.models import Organization, Site
from terrasatch.outbound.models import OutboundStatus
from terrasatch.satchy.models import FieldAsset, FieldMission


async def _mission_fixture():
    engine, session, seeded = await _seed_session()
    organization = seeded["organization"]
    site = seeded["site"]
    device = seeded["devices"][0]
    api_key = seeded["keys"][0]

    assert isinstance(organization, Organization)
    assert isinstance(site, Site)
    assert isinstance(device, EdgeDevice)

    _, action = await _ingest(session, seeded, "Satchy, Control 2.")
    action.action_type = ActionType.ASSET_MISSION.value
    action.status = ActionStatus.QUEUED.value
    action.proposed_message = None

    asset = FieldAsset(
        organization_id=organization.id,
        site_id=site.id,
        controller_edge_device_id=device.id,
        name="QA Drone",
        asset_type="drone",
        provider="qa",
        capabilities=["camera:capture"],
        state="available",
        enabled=True,
    )
    session.add(asset)
    await session.flush()

    command = EdgeCommand(
        organization_id=organization.id,
        site_id=site.id,
        edge_device_id=device.id,
        command_type="asset_mission",
        payload={},
        priority=50,
        status="queued",
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    session.add(command)
    await session.flush()

    mission = FieldMission(
        organization_id=organization.id,
        site_id=site.id,
        asset_id=asset.id,
        action_id=action.id,
        edge_command_id=command.id,
        objective="Inspect Cardiff Bowl",
        mission_type="inspection",
        required_capabilities=["camera:capture"],
        target={"location_text": "Cardiff Bowl"},
        approval_required=True,
        status="queued",
    )
    session.add(mission)
    await session.flush()

    command.payload = {"mission_id": str(mission.id)}
    await session.flush()

    kwargs = {
        "organization_id": organization.id,
        "api_key_id": api_key.id,
        "command_id": command.id,
    }
    return engine, session, action, command, mission, kwargs


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("result", "mission_status", "command_status", "action_status"),
    [
        ("completed", "completed", "completed", ActionStatus.COMPLETED.value),
        ("aborted", "aborted", "completed", ActionStatus.CANCELLED.value),
        ("failed", "failed", "failed", ActionStatus.FAILED.value),
    ],
)
async def test_asset_mission_edge_lifecycle_updates_linked_records(
    result: str,
    mission_status: str,
    command_status: str,
    action_status: str,
) -> None:
    engine, session, action, command, mission, kwargs = await _mission_fixture()
    try:
        acknowledged = await acknowledge_command(session, **kwargs)

        assert acknowledged.status == "acknowledged"
        assert acknowledged.acknowledged_at is not None
        assert mission.status == "deploying"
        assert mission.started_at is not None
        assert action.status == ActionStatus.EXECUTING.value

        completed = await complete_command(
            session,
            **kwargs,
            result=result,
            detail="QA operator result",
        )

        assert completed.status == command_status
        assert completed.completed_at is not None
        assert completed.payload["result"] == result
        assert completed.payload["result_detail"] == "QA operator result"
        assert mission.status == mission_status
        assert mission.completed_at is not None
        assert mission.result == {
            "status": result,
            "detail": "QA operator result",
        }
        assert action.status == action_status
    finally:
        await session.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_poll_expires_queued_radio_command_and_linked_records() -> None:
    engine, session, seeded = await _seed_session()
    try:
        organization = seeded["organization"]
        api_key = seeded["keys"][0]
        assert isinstance(organization, Organization)

        _, action = await _ingest(session, seeded, "Satchy, Control 2.")
        action, _, outbound, command = await approve_and_queue_action(
            session,
            organization_id=organization.id,
            action_id=action.id,
            approver_role="admin",
        )
        command.expires_at = datetime.now(UTC) - timedelta(seconds=1)

        visible = await list_device_commands(
            session,
            organization_id=organization.id,
            api_key_id=api_key.id,
        )

        assert visible == []
        assert command.status == "expired"
        assert outbound.status == OutboundStatus.EXPIRED.value
        assert action.status == ActionStatus.EXPIRED.value
    finally:
        await session.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_command_result_requires_supported_value_and_acknowledgement() -> None:
    engine, session, seeded = await _seed_session()
    try:
        organization = seeded["organization"]
        api_key = seeded["keys"][0]
        assert isinstance(organization, Organization)

        _, action = await _ingest(session, seeded, "Satchy, Control 2.")
        _, _, _, command = await approve_and_queue_action(
            session,
            organization_id=organization.id,
            action_id=action.id,
            approver_role="admin",
        )
        kwargs = {
            "organization_id": organization.id,
            "api_key_id": api_key.id,
            "command_id": command.id,
        }

        with pytest.raises(InvalidConfiguration, match="Unsupported"):
            await complete_command(session, **kwargs, result="not-a-result")

        with pytest.raises(InvalidConfiguration, match="acknowledged"):
            await complete_command(session, **kwargs, result="simulated")
    finally:
        await session.close()
        await engine.dispose()
