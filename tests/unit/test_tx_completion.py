from datetime import UTC, datetime, timedelta

import pytest
from test_satchy_control_plane import _ingest, _seed_session

from terrasatch.actions.service import approve_and_queue_action
from terrasatch.edge.command_service import (
    acknowledge_command,
    complete_command,
    list_device_commands,
)
from terrasatch.errors import InvalidConfiguration


async def rf_fixture():
    engine, session, seeded = await _seed_session()
    device = seeded['devices'][0]
    device.last_seen_at = datetime.now(UTC)
    device.capabilities = ['radio:transmit']
    device.remote_config = {'radio': {'transmit_enabled': True, 'ai_channel': {
        'rf_reply_enabled': True, 'reply_route': 'rf',
    }}}
    _, action = await _ingest(session, seeded, 'Satchy, Control 2.')
    _, _, outbound, command = await approve_and_queue_action(
        session, organization_id=device.organization_id, action_id=action.id, approver_role='admin')
    kwargs = dict(organization_id=device.organization_id, api_key_id=seeded['keys'][0].id,
                  command_id=command.id)
    return engine, session, seeded, action, outbound, command, kwargs


@pytest.mark.asyncio
@pytest.mark.parametrize('result', ['transmitted', 'failed'])
async def test_real_result_is_distinct_idempotent_and_immutable(result):
    engine, session, _, action, outbound, command, kwargs = await rf_fixture()
    try:
        await acknowledge_command(session, **kwargs)
        await complete_command(session, **kwargs, result=result)
        completed = command.completed_at
        await complete_command(session, **kwargs, result=result)
        assert command.completed_at == completed
        assert outbound.status == result
        assert (outbound.transmitted_at is not None) == (result == 'transmitted')
        assert action.status == ('completed' if result == 'transmitted' else 'failed')
        with pytest.raises(InvalidConfiguration):
            await complete_command(session, **kwargs, result='simulated')
    finally:
        await session.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_late_result_reconciles_acknowledged_operation_after_expiry():
    engine, session, _, action, outbound, command, kwargs = await rf_fixture()
    try:
        await acknowledge_command(session, **kwargs)
        past = datetime.now(UTC) - timedelta(minutes=1)
        command.expires_at = action.expires_at = past
        rows = await list_device_commands(session, organization_id=kwargs['organization_id'],
                                         api_key_id=kwargs['api_key_id'])
        assert rows[0].id == command.id
        assert command.status == 'acknowledged'
        await complete_command(session, **kwargs, result='transmitted')
        assert outbound.status == 'transmitted'
        assert action.status == 'completed'
    finally:
        await session.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_revoked_rf_policy_rejects_ack_before_execution():
    engine, session, seeded, _, _, command, kwargs = await rf_fixture()
    try:
        seeded['devices'][0].remote_config = {}
        with pytest.raises(InvalidConfiguration, match='revoked'):
            await acknowledge_command(session, **kwargs)
        assert command.status == 'queued'
    finally:
        await session.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_rf_reply_cannot_be_misreported_as_simulation():
    engine, session, _, _, _, _, kwargs = await rf_fixture()
    try:
        await acknowledge_command(session, **kwargs)
        with pytest.raises(InvalidConfiguration, match='simulated'):
            await complete_command(session, **kwargs, result='simulated')
    finally:
        await session.close()
        await engine.dispose()
