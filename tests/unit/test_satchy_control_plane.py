from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from terrasatch.actions import models as action_models
from terrasatch.actions.models import ActionStatus, ActionType, SatchyAction, SatchyEvaluation
from terrasatch.actions.service import (
    approve_action,
    approve_and_queue_action,
    queue_approved_action,
)
from terrasatch.actions.state import transition_action
from terrasatch.admin.ai_channel import rf_reply_policy_allows
from terrasatch.auth import models as auth_models
from terrasatch.auth.models import ApiKey
from terrasatch.config import Settings
from terrasatch.database.base import Base
from terrasatch.edge import models as edge_models
from terrasatch.edge.command_service import (
    acknowledge_command,
    complete_command,
    list_device_commands,
)
from terrasatch.edge.models import EdgeCommand, EdgeDevice
from terrasatch.errors import InvalidConfiguration, ResourceNotFound, TenantAccessDenied
from terrasatch.identity import models as identity_models
from terrasatch.identity.models import Account, Organization, Site
from terrasatch.masterdata import models as masterdata_models
from terrasatch.organizations import models as organization_models
from terrasatch.outbound import models as outbound_models
from terrasatch.outbound.models import OutboundTransmission
from terrasatch.radio import models as radio_models
from terrasatch.radio.addressing import CallsignCandidate, parse_radio_addressing
from terrasatch.radio.models import Agent, Callsign, Channel, Transmission
from terrasatch.radio.schemas import TransmissionCreateRequest
from terrasatch.radio.service import ingest_transmission

_MODEL_MODULES = (
    action_models,
    auth_models,
    edge_models,
    identity_models,
    masterdata_models,
    organization_models,
    outbound_models,
    radio_models,
)


async def _seed_session() -> tuple[object, AsyncSession, dict[str, object]]:
    assert _MODEL_MODULES
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    session = sessions()

    account = Account(name="Satchy control plane tests")
    session.add(account)
    await session.flush()
    organization = Organization(
        account_id=account.id,
        name="UAC",
        slug=f"uac-{uuid4().hex[:8]}",
        enabled=True,
    )
    session.add(organization)
    await session.flush()
    site = Site(
        organization_id=organization.id,
        name="Snowbird",
        slug=f"snowbird-{uuid4().hex[:8]}",
        enabled=True,
    )
    session.add(site)
    await session.flush()
    agent = Agent(
        organization_id=organization.id,
        site_id=site.id,
        name="Satchy",
        slug=f"satchy-{uuid4().hex[:8]}",
        profile="terralisten",
        enabled=True,
    )
    session.add(agent)
    await session.flush()
    channel = Channel(
        organization_id=organization.id,
        site_id=site.id,
        agent_id=agent.id,
        name="Operations 2",
        slug=f"operations-2-{uuid4().hex[:8]}",
        profile="terralisten",
        enabled=True,
    )
    session.add(channel)
    satchy = Callsign(
        organization_id=organization.id,
        site_id=site.id,
        name="Satchy",
        aliases=["TerraSatch"],
        enabled=True,
    )
    control = Callsign(
        organization_id=organization.id,
        site_id=site.id,
        name="Control 2",
        aliases=["Control Two"],
        enabled=True,
    )
    session.add_all((satchy, control))

    keys: list[ApiKey] = []
    devices: list[EdgeDevice] = []
    for index in range(2):
        key = ApiKey(
            organization_id=organization.id,
            name=f"Edge {index}",
            key_prefix=f"edge-{uuid4().hex[:12]}",
            secret_hash=uuid4().hex,
            scopes=["edge:connect", "edge:ingest"],
        )
        session.add(key)
        await session.flush()
        device = EdgeDevice(
            organization_id=organization.id,
            site_id=site.id,
            api_key_id=key.id,
            name=f"Edge {index}",
            capabilities=["radio:receive"],
            remote_config={},
            enabled=True,
        )
        session.add(device)
        keys.append(key)
        devices.append(device)
    await session.flush()
    return (
        engine,
        session,
        {
            "organization": organization,
            "site": site,
            "agent": agent,
            "channel": channel,
            "satchy": satchy,
            "control": control,
            "keys": keys,
            "devices": devices,
        },
    )


async def _ingest(
    session: AsyncSession,
    seeded: dict[str, object],
    text: str,
) -> tuple[Transmission, SatchyAction]:
    organization = seeded["organization"]
    site = seeded["site"]
    agent = seeded["agent"]
    channel = seeded["channel"]
    assert isinstance(organization, Organization)
    assert isinstance(site, Site)
    assert isinstance(agent, Agent)
    assert isinstance(channel, Channel)
    transmission, _transcript, _events, duplicate = await ingest_transmission(
        session,
        settings=Settings(intelligence_provider="deterministic"),
        organization_id=organization.id,
        payload=TransmissionCreateRequest(
            site_id=site.id,
            agent_id=agent.id,
            channel_id=channel.id,
            text=text,
            source="terrasatch-edge-stt",
            source_message_id=f"satchy-{uuid4()}",
            transcript_provider="faster_whisper",
        ),
    )
    assert duplicate is False
    action = await session.scalar(
        select(SatchyAction).where(SatchyAction.source_transmission_id == transmission.id)
    )
    assert action is not None
    return transmission, action


def test_recipient_first_radio_order_is_deterministic() -> None:
    satchy_id = uuid4()
    control_id = uuid4()
    candidates = [
        CallsignCandidate(id=satchy_id, name="Satchy"),
        CallsignCandidate(id=control_id, name="Control 2", aliases=("Control Two",)),
    ]

    inbound = parse_radio_addressing(
        "Satchy, Control 2.", callsigns=candidates, agent_names={"Satchy"}
    )
    outbound = parse_radio_addressing(
        "Control 2, Satchy.", callsigns=candidates, agent_names={"Satchy"}
    )

    assert inbound.recipient_callsign_id == satchy_id
    assert inbound.speaker_callsign_id == control_id
    assert inbound.addressed_to_agent is True
    assert inbound.confidence == 0.94
    assert outbound.recipient_callsign_id == control_id
    assert outbound.speaker_callsign_id == satchy_id
    assert outbound.addressed_to_agent is False


@pytest.mark.asyncio
async def test_ingest_associates_conversation_and_proposes_expected_reply() -> None:
    engine, session, seeded = await _seed_session()
    try:
        first, first_action = await _ingest(session, seeded, "Satchy, Control 2.")
        second, _ = await _ingest(session, seeded, "Satchy, Control 2. Status update.")
        evaluation = await session.scalar(
            select(SatchyEvaluation).where(SatchyEvaluation.source_transmission_id == first.id)
        )

        assert first.recipient_callsign_id == seeded["satchy"].id  # type: ignore[union-attr]
        assert first.speaker_callsign_id == seeded["control"].id  # type: ignore[union-attr]
        assert first.addressed_to_agent is True
        assert first.conversation_id == second.conversation_id
        assert first_action.status == ActionStatus.AWAITING_APPROVAL.value
        assert first_action.proposed_message == "Control 2, Satchy. Go ahead."
        assert evaluation is not None
        assert evaluation.proposed_action == {
            "type": "reply_radio",
            "message": "Control 2, Satchy. Go ahead.",
        }
    finally:
        await session.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_approval_gate_and_simulated_edge_lifecycle_are_idempotent() -> None:
    engine, session, seeded = await _seed_session()
    try:
        organization = seeded["organization"]
        keys = seeded["keys"]
        assert isinstance(organization, Organization)
        assert isinstance(keys, list)
        _transmission, action = await _ingest(session, seeded, "Satchy, Control 2.")

        with pytest.raises(InvalidConfiguration, match="approved"):
            await queue_approved_action(
                session,
                organization_id=organization.id,
                action_id=action.id,
            )

        action, _approval, outbound, command = await approve_and_queue_action(
            session,
            organization_id=organization.id,
            action_id=action.id,
            approver_role="admin",
        )
        assert action.status == ActionStatus.QUEUED.value
        assert outbound.status == "queued"
        assert outbound.reply_route == "simulation"
        assert command.payload["simulate_only"] is True

        with pytest.raises(ResourceNotFound):
            await acknowledge_command(
                session,
                organization_id=organization.id,
                api_key_id=keys[1].id,
                command_id=command.id,
            )

        visible = await list_device_commands(
            session,
            organization_id=organization.id,
            api_key_id=keys[0].id,
        )
        assert [item.id for item in visible] == [command.id]
        assert command.status == "dispatched"

        first_ack = await acknowledge_command(
            session,
            organization_id=organization.id,
            api_key_id=keys[0].id,
            command_id=command.id,
        )
        acknowledged_at = first_ack.acknowledged_at
        second_ack = await acknowledge_command(
            session,
            organization_id=organization.id,
            api_key_id=keys[0].id,
            command_id=command.id,
        )
        assert second_ack.acknowledged_at == acknowledged_at
        assert outbound.status == "edge_received"
        assert action.status == ActionStatus.EXECUTING.value

        first_result = await complete_command(
            session,
            organization_id=organization.id,
            api_key_id=keys[0].id,
            command_id=command.id,
            result="simulated",
        )
        completed_at = first_result.completed_at
        second_result = await complete_command(
            session,
            organization_id=organization.id,
            api_key_id=keys[0].id,
            command_id=command.id,
            result="simulated",
        )
        assert second_result.completed_at == completed_at
        assert outbound.status == "simulated"
        assert action.status == ActionStatus.COMPLETED.value
        assert await session.scalar(select(func.count(OutboundTransmission.id))) == 1
        assert await session.scalar(select(func.count(EdgeCommand.id))) == 1
    finally:
        await session.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_unauthorized_and_cross_tenant_approval_are_rejected() -> None:
    engine, session, seeded = await _seed_session()
    try:
        organization = seeded["organization"]
        assert isinstance(organization, Organization)
        _transmission, action = await _ingest(session, seeded, "Satchy, Control 2.")
        with pytest.raises(TenantAccessDenied):
            await approve_action(
                session,
                organization_id=organization.id,
                action_id=action.id,
                approver_role="viewer",
            )
        with pytest.raises(ResourceNotFound):
            await approve_action(
                session,
                organization_id=uuid4(),
                action_id=action.id,
                approver_role="admin",
            )
        assert action.status == ActionStatus.AWAITING_APPROVAL.value
    finally:
        await session.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_emergency_candidate_never_creates_outbound_automatically() -> None:
    engine, session, seeded = await _seed_session()
    try:
        transmission, action = await _ingest(
            session, seeded, "Satchy emergency, broken leg, I'm alone."
        )
        assert transmission.emergency_candidate is True
        assert action.action_type == ActionType.EMERGENCY_REVIEW.value
        assert action.risk_level == "critical"
        assert action.status == ActionStatus.AWAITING_APPROVAL.value
        assert await session.scalar(select(func.count(OutboundTransmission.id))) == 0
        assert await session.scalar(select(func.count(EdgeCommand.id))) == 0
    finally:
        await session.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_expired_command_cannot_acknowledge_or_execute() -> None:
    engine, session, seeded = await _seed_session()
    try:
        organization = seeded["organization"]
        keys = seeded["keys"]
        assert isinstance(organization, Organization)
        assert isinstance(keys, list)
        _transmission, action = await _ingest(session, seeded, "Satchy, Control 2.")
        _, _, _, command = await approve_and_queue_action(
            session,
            organization_id=organization.id,
            action_id=action.id,
            approver_role="admin",
        )
        command.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        with pytest.raises(InvalidConfiguration, match="Expired"):
            await acknowledge_command(
                session,
                organization_id=organization.id,
                api_key_id=keys[0].id,
                command_id=command.id,
            )
    finally:
        await session.close()
        await engine.dispose()


def test_invalid_state_transition_and_rf_policy_are_rejected() -> None:
    action = SimpleNamespace(
        status=ActionStatus.PROPOSED.value,
        expires_at=None,
        approved_at=None,
        executed_at=None,
    )
    with pytest.raises(InvalidConfiguration, match="proposed -> queued"):
        transition_action(action, ActionStatus.QUEUED)  # type: ignore[arg-type]

    no_capability = SimpleNamespace(
        capabilities=["radio:receive"],
        remote_config={
            "radio": {
                "transmit_enabled": True,
                "ai_channel": {"reply_route": "rf", "rf_reply_enabled": True},
            }
        },
    )
    no_policy = SimpleNamespace(
        capabilities=["radio:transmit"],
        remote_config={
            "radio": {
                "transmit_enabled": False,
                "ai_channel": {"reply_route": "rf", "rf_reply_enabled": True},
            }
        },
    )
    assert rf_reply_policy_allows(no_capability) is False  # type: ignore[arg-type]
    assert rf_reply_policy_allows(no_policy) is False  # type: ignore[arg-type]
