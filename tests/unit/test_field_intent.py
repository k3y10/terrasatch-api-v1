from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from test_natural_radio import ingest
from test_satchy_control_plane import _seed_session

from terrasatch.actions.evaluation import process_transmission_control_plane
from terrasatch.actions.field_intent import classify_field_intent, location_candidates
from terrasatch.actions.models import SatchyAction, SatchyEvaluation
from terrasatch.edge.models import EdgeCommand
from terrasatch.organizations.models import OrganizationOperationalProfile
from terrasatch.outbound.models import OutboundTransmission
from terrasatch.radio.models import OperationalEvent


@pytest.mark.parametrize(
    "command,expected",
    [
        ("log this observation.", "create_observation"),
        ("log an observation at Cardiff Bowl.", "create_observation"),
        ("record this.", "create_observation"),
        ("note that winds increased around 1400.", "create_observation"),
        ("add that to the current event.", "update_event"),
        ("add that to the current incident.", "update_event"),
        ("update the event with that observation.", "update_event"),
        ("notify Base about that.", "notify_team"),
        ("prepare my report.", "generate_report"),
        ("prepare my field report.", "generate_report"),
        ("prepare my shift handoff.", "generate_report"),
        ("prepare my handoff.", "generate_report"),
        ("summarize my observations.", "generate_report"),
        ("summarize my observations from today.", "generate_report"),
        ("how copy?", "reply_radio"),
        ("", "reply_radio"),
        ("log.", "ask_clarification"),
        ("Do not notify Base.", None),
        ("Base asked us to prepare my report.", None),
        ("Observation at Cardiff Bowl. Wind loading.", None),
        ("Snowpit at 9,600 feet northeast aspect.", None),
        ("Field observation at Cardiff Bowl. Light wind.", None),
        ("Note for end-of-shift report: winds increased.", "create_observation"),
    ],
)
def test_command_rules(command, expected):
    assert classify_field_intent(command) == expected


@pytest.mark.parametrize(
    "command,expected",
    [
        ("log this observation.", "create_observation"),
        ("add that to the current event.", "update_event"),
        ("notify Base about that.", "notify_team"),
        ("prepare my report.", "generate_report"),
        ("prepare my shift handoff.", "generate_report"),
        ("summarize my observations.", "generate_report"),
        ("how copy?", "reply_radio"),
        ("Observation at Cardiff Bowl. Light wind.", None),
        ("Snowpit at 9,600 feet northeast aspect. No cracking.", None),
    ],
)
async def test_workflow_ingest(command, expected):
    engine, session, seed = await _seed_session()
    try:
        tx, _, events, _ = await ingest(session, seed, "Satchy, Control Two, " + command)
        actions = list(
            await session.scalars(
                select(SatchyAction).where(SatchyAction.source_transmission_id == tx.id)
            )
        )
        assert len(actions) == (1 if expected else 0)
        assert await session.scalar(select(func.count(OperationalEvent.id))) == len(events)
        if actions:
            action = actions[0]
            assert action.action_type == expected
            assert action.status == "awaiting_approval"
            assert action.approval_required
            assert action.operational_event_id == events[0].id
            if expected != "reply_radio":
                assert action.structured_payload["source_transmission_id"] == str(tx.id)
                assert action.structured_payload["site_id"] == str(seed["site"].id)
                assert action.proposed_message is None
        outcome = await process_transmission_control_plane(
            session,
            transmission=tx,
            text="Satchy, Control Two, " + command,
            callsign_hint=None,
            operational_event=events[0],
        )
        assert outcome.action == (actions[0] if actions else None)
        assert await session.scalar(select(func.count(SatchyEvaluation.id))) == 1
        assert await session.scalar(select(func.count(OutboundTransmission.id))) == 0
        assert await session.scalar(select(func.count(EdgeCommand.id))) == 0
    finally:
        await session.close()
        await engine.dispose()


async def test_report_snapshot_uses_operator_site_and_time():
    engine, session, seed = await _seed_session()
    try:
        now = datetime(2026, 9, 4, 16, tzinfo=UTC)
        good, _, events, _ = await ingest(
            session,
            seed,
            "Field observation at Cardiff Bowl. Light wind.",
            callsign="Control Two",
            received_at=now - timedelta(hours=2),
        )
        old, _, _, _ = await ingest(
            session,
            seed,
            "Old observation.",
            callsign="Control 2",
            received_at=now - timedelta(days=1),
        )
        other, _, _, _ = await ingest(
            session, seed, "Other operator.", callsign="Other", received_at=now - timedelta(hours=1)
        )
        future, _, _, _ = await ingest(
            session,
            seed,
            "Future observation.",
            callsign="Control 2",
            received_at=now + timedelta(hours=1),
        )
        tx, _, _, _ = await ingest(
            session, seed, "Satchy, Control 2, prepare my shift handoff.", received_at=now
        )
        action = await session.scalar(
            select(SatchyAction).where(SatchyAction.source_transmission_id == tx.id)
        )
        payload = action.structured_payload
        assert payload["transmission_ids"] == [str(good.id)]
        assert payload["operational_event_ids"] == [str(events[0].id)]
        assert payload["report_kind"] == "handoff"
        assert payload["scope"]["timezone"] == "UTC"
        assert payload["scope"]["requires_time_window_confirmation"]
        assert not payload["truncated"]
        assert all(str(item.id) not in payload["transmission_ids"] for item in [old, other, future])
    finally:
        await session.close()
        await engine.dispose()


async def test_ambiguous_location_and_unknown_report_operator_require_clarification():
    engine, session, seed = await _seed_session()
    try:
        session.add(
            OrganizationOperationalProfile(
                organization_id=seed["organization"].id,
                site_id=seed["site"].id,
                location_aliases={"Cardiff Bowl": ["Cardiff"], "Cardiff Fork": ["Cardiff"]},
            )
        )
        await session.flush()
        for text in ["Satchy, log that at Cardiff.", "Satchy, prepare my handoff."]:
            tx, _, _, _ = await ingest(session, seed, text)
            action = await session.scalar(
                select(SatchyAction).where(SatchyAction.source_transmission_id == tx.id)
            )
            assert action.action_type == "ask_clarification"
            assert action.structured_payload["clarification_reason"]
    finally:
        await session.close()
        await engine.dispose()


def test_location_matching_prefers_exact_and_preserves_ambiguity():
    aliases = {"Cardiff Bowl": ["Bowl"], "Cardiff Fork": []}
    assert location_candidates("log that at Cardiff.", aliases) == ["Cardiff Bowl", "Cardiff Fork"]
    assert location_candidates("log that at Cardiff Bowl.", aliases) == ["Cardiff Bowl"]
    assert location_candidates("log that at Bowl.", aliases) == ["Cardiff Bowl"]


@pytest.mark.parametrize(
    "text",
    [
        "Satchy, Control 2, emergency, broken leg.",
        "Control 2 to Satchy, mayday.",
        "Field observation, serious injury at Cardiff Bowl.",
    ],
)
async def test_emergency_overrides_intent_and_addressing(text):
    engine, session, seed = await _seed_session()
    try:
        tx, _, _, _ = await ingest(session, seed, text)
        action = await session.scalar(
            select(SatchyAction).where(SatchyAction.source_transmission_id == tx.id)
        )
        assert tx.emergency_candidate
        assert action.action_type == "emergency_review"
        assert action.status == "awaiting_approval"
        assert await session.scalar(select(func.count(OutboundTransmission.id))) == 0
    finally:
        await session.close()
        await engine.dispose()


async def test_workflow_policy_can_disable_proposals():
    engine, session, seed = await _seed_session()
    try:
        for policy in [
            {"response_mode": "listen_only"},
            {"allowed_action_types": ["reply_radio"]},
        ]:
            for device in seed["devices"]:
                device.remote_config = {"radio": {"ai_channel": policy}}
            await session.flush()
            tx, _, events, _ = await ingest(session, seed, "Satchy, Control 2, prepare my handoff.")
            assert events
            assert (
                await session.scalar(
                    select(SatchyAction).where(SatchyAction.source_transmission_id == tx.id)
                )
                is None
            )
    finally:
        await session.close()
        await engine.dispose()


async def test_update_target_requires_unique_scoped_incident():
    engine, session, seed = await _seed_session()
    try:

        async def update():
            tx, _, _, _ = await ingest(
                session, seed, "Satchy, Control 2, add that to the current event."
            )
            return await session.scalar(
                select(SatchyAction).where(SatchyAction.source_transmission_id == tx.id)
            )

        empty = await update()
        assert empty.action_type == "update_event"
        assert empty.structured_payload["requires_target_selection"]
        _, _, events, _ = await ingest(session, seed, "Satchy, Control 2, injury with broken leg.")
        unique = await update()
        assert unique.structured_payload["target_event_id"] == str(events[0].id)
        assert not unique.structured_payload["requires_target_selection"]
        await ingest(session, seed, "Satchy, Control 2, injury with broken leg.")
        ambiguous = await update()
        assert ambiguous.structured_payload["requires_target_selection"]
        assert ambiguous.structured_payload["target_event_id"] is None
    finally:
        await session.close()
        await engine.dispose()


async def test_report_does_not_include_other_sites_or_tenants():
    from types import SimpleNamespace
    from uuid import uuid4

    from terrasatch.identity.models import Organization, Site
    from terrasatch.radio.models import Callsign

    engine, session, seed = await _seed_session()
    try:
        # An organization-wide callsign may validly operate at more than one site.
        seed["control"].site_id = None
        for cross_tenant in [False, True]:
            org = seed["organization"]
            if cross_tenant:
                org = Organization(
                    account_id=org.account_id, name="Other", slug="other-report", enabled=True
                )
                session.add(org)
                await session.flush()
            site = Site(organization_id=org.id, name="Remote", slug=str(uuid4()), enabled=True)
            session.add(site)
            await session.flush()
            if cross_tenant:
                session.add(
                    Callsign(
                        organization_id=org.id,
                        site_id=site.id,
                        name="Control 2",
                        aliases=["Control Two"],
                        enabled=True,
                    )
                )
                await session.flush()
            remote_seed = {
                **seed,
                "organization": org,
                "site": site,
                "agent": SimpleNamespace(id=None),
                "channel": SimpleNamespace(id=None),
            }
            await ingest(
                session, remote_seed, "Weather observation. Light wind.", callsign="Control Two"
            )
        tx, _, _, _ = await ingest(session, seed, "Satchy, Control 2, prepare my report.")
        action = await session.scalar(
            select(SatchyAction).where(SatchyAction.source_transmission_id == tx.id)
        )
        assert action.structured_payload["transmission_ids"] == []
        assert action.structured_payload["operational_event_ids"] == []
    finally:
        await session.close()
        await engine.dispose()
