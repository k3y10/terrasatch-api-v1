from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from terrasatch.actions import models as action_models
from terrasatch.auth import models as auth_models
from terrasatch.config import Settings
from terrasatch.database.base import Base
from terrasatch.edge import models as edge_models
from terrasatch.errors import TenantAccessDenied
from terrasatch.identity import models as identity_models
from terrasatch.identity.models import (
    Account,
    Membership,
    MembershipRole,
    Organization,
    Site,
    Team,
    User,
)
from terrasatch.organizations import models as organization_models
from terrasatch.outbound import models as outbound_models
from terrasatch.radio import models as radio_models
from terrasatch.satchy import models as satchy_models
from terrasatch.satchy.adaptation import observe_workspace_context
from terrasatch.satchy.agent import plan_integration_action, resolve_radio_intent
from terrasatch.satchy.assets import (
    create_mission_plan,
    list_authorized_assets,
    select_asset_for_capabilities,
)
from terrasatch.satchy.context import build_satchy_context
from terrasatch.satchy.intents import resolve_intent
from terrasatch.satchy.models import FieldAsset
from terrasatch.satchy.schemas import ActiveMapContext, SatchyIntent, WorkflowMode
from terrasatch.satchy.workflows import resolve_workflow
from terrasatch.workspace import models as workspace_models
from terrasatch.workspace.models import WorkspacePreference

_MODEL_MODULES = (
    action_models,
    auth_models,
    edge_models,
    identity_models,
    organization_models,
    outbound_models,
    radio_models,
    satchy_models,
    workspace_models,
)


def test_radio_intent_and_workflow_are_conservative() -> None:
    log = resolve_intent("Satchy, log that last report.")
    approve = resolve_intent("Satchy, Control 2. Approve.")
    mission = resolve_intent("Satchy, get eyes on Cardiff.")
    notify = resolve_intent("Satchy, notify the team that Cardiff is clear.")
    report = resolve_intent("Satchy, generate a shift report.")

    assert log.intent == SatchyIntent.LOG_OBSERVATION
    assert log.references_context is True
    assert resolve_workflow(log) == WorkflowMode.AUTO_COMPLETE

    assert approve.intent == SatchyIntent.APPROVE_ACTION
    assert resolve_workflow(approve) == WorkflowMode.CONFIRM
    assert resolve_intent("Satchy, Control 2. Do not approve.").intent == SatchyIntent.REJECT_ACTION

    assert notify.intent == SatchyIntent.REQUEST_ACTION
    assert report.intent == SatchyIntent.REQUEST_ACTION

    assert mission.intent == SatchyIntent.REQUEST_MISSION
    assert resolve_workflow(mission) == WorkflowMode.CONFIRM
    assert (
        resolve_workflow(mission, preauthorized=True)
        == WorkflowMode.AUTO_COMPLETE
    )
    assert (
        resolve_workflow(
            log,
            missing_critical_context=["location"],
        )
        == WorkflowMode.CLARIFY
    )


@pytest.mark.asyncio
async def test_integration_planner_is_provider_neutral_and_always_approval_gated() -> None:
    settings = Settings(intelligence_provider="deterministic")
    notify = await plan_integration_action(
        settings=settings,
        text="Satchy, notify the team that Cardiff is clear.",
        context={},
    )
    assert notify.action_type == "notify_team"
    assert notify.notification_text == "Cardiff is clear"
    assert notify.approval_required is True
    assert "slack" not in str(notify.model_dump()).casefold()

    report = await plan_integration_action(
        settings=settings,
        text="Satchy, generate a shift handoff.",
        context={
            "conversation": {
                "active_location": "Cardiff Bowl",
                "summaries": [
                    "No avalanche activity observed.",
                    "Wind transport increasing along the ridge.",
                ],
            }
        },
    )
    assert report.action_type == "generate_report"
    assert report.document_name == "satchy-shift-handoff.md"
    assert "Cardiff Bowl" in (report.document_content or "")
    assert "No avalanche activity observed" in (report.document_content or "")
    assert report.approval_required is True
    assert "google" not in str(report.model_dump()).casefold()


def test_workspace_adaptation_records_usage_without_precise_map_location() -> None:
    preference = WorkspacePreference(
        organization_id=uuid4(),
        user_id=uuid4(),
        modules=["Map", "Satchy"],
        satchy_preferences={"explicit": {"response_detail": "brief"}},
    )
    site_id = uuid4()
    active_map = ActiveMapContext(
        map_id="avalanche",
        center_latitude=40.1234,
        center_longitude=-111.5678,
        zoom=14,
        selected_layers=["slope_angle", "observations"],
        selected_terrain="Cardiff Bowl",
    )

    observe_workspace_context(preference, site_id=site_id, active_map=active_map)
    observe_workspace_context(preference, site_id=site_id, active_map=active_map)

    observed = preference.satchy_preferences["observed"]
    assert observed["site_counts"][str(site_id)] == 2
    assert observed["map_counts"]["avalanche"] == 2
    assert observed["layer_counts"]["slope_angle"] == 2
    assert observed["layer_counts"]["observations"] == 2
    serialized = str(preference.satchy_preferences)
    assert "40.1234" not in serialized
    assert "-111.5678" not in serialized
    assert "Cardiff Bowl" not in serialized


@pytest.mark.asyncio
async def test_assets_are_scoped_and_preauthorized_mission_can_be_planned() -> None:
    assert _MODEL_MODULES
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        account = Account(name="Satchy assets")
        session.add(account)
        await session.flush()
        org = Organization(
            account_id=account.id,
            name="Field Org",
            slug=f"field-{uuid4().hex[:8]}",
            enabled=True,
        )
        other_org = Organization(
            account_id=account.id,
            name="Other Org",
            slug=f"other-{uuid4().hex[:8]}",
            enabled=True,
        )
        session.add_all((org, other_org))
        await session.flush()
        site = Site(
            organization_id=org.id,
            name="Cardiff",
            slug=f"cardiff-{uuid4().hex[:8]}",
            enabled=True,
        )
        other_site = Site(
            organization_id=other_org.id,
            name="Elsewhere",
            slug=f"elsewhere-{uuid4().hex[:8]}",
            enabled=True,
        )
        session.add_all((site, other_site))
        await session.flush()

        user = User(email=f"{uuid4().hex}@example.com", display_name="Field One", enabled=True)
        other_user = User(
            email=f"{uuid4().hex}@example.com",
            display_name="Field Two",
            enabled=True,
        )
        session.add_all((user, other_user))
        await session.flush()
        team = Team(organization_id=org.id, site_id=site.id, name="Patrol", enabled=True)
        session.add(team)
        await session.flush()

        shared = FieldAsset(
            organization_id=org.id,
            site_id=site.id,
            name="Cardiff Camera",
            asset_type="camera",
            provider="camera-test",
            capabilities=["camera:capture"],
            state="available",
            policy={
                "autonomous_mission_types": ["inspection"],
                "mission_execution_enabled": True,
            },
            enabled=True,
        )
        personal = FieldAsset(
            organization_id=org.id,
            site_id=site.id,
            owner_user_id=user.id,
            name="Personal Sensor",
            asset_type="sensor",
            provider="sensor-test",
            capabilities=["sensor:weather"],
            state="available",
            enabled=True,
        )
        someone_elses = FieldAsset(
            organization_id=org.id,
            site_id=site.id,
            owner_user_id=other_user.id,
            name="Other Personal Drone",
            asset_type="drone",
            provider="drone-test",
            capabilities=["drone:mission"],
            state="available",
            enabled=True,
        )
        team_only = FieldAsset(
            organization_id=org.id,
            site_id=site.id,
            team_id=team.id,
            name="Patrol Drone",
            asset_type="drone",
            provider="drone-test",
            capabilities=["drone:mission"],
            state="available",
            enabled=True,
        )
        foreign = FieldAsset(
            organization_id=other_org.id,
            site_id=other_site.id,
            name="Foreign Camera",
            asset_type="camera",
            provider="camera-test",
            capabilities=["camera:capture"],
            state="available",
            enabled=True,
        )
        session.add_all((shared, personal, someone_elses, team_only, foreign))
        await session.flush()

        visible = await list_authorized_assets(
            session,
            organization_id=org.id,
            site_id=site.id,
            user_id=user.id,
        )
        assert {item.name for item in visible} == {"Cardiff Camera", "Personal Sensor"}

        camera = await select_asset_for_capabilities(
            session,
            organization_id=org.id,
            site_id=site.id,
            user_id=user.id,
            required_capabilities={"camera:capture"},
        )
        assert camera is not None
        assert camera.id == shared.id

        mission = await create_mission_plan(
            session,
            organization_id=org.id,
            site_id=site.id,
            requested_by_user_id=user.id,
            objective="Get eyes on Cardiff",
            mission_type="inspection",
            required_capabilities={"camera:capture"},
            target={"location": "Cardiff Bowl"},
        )
        assert mission.asset_id == shared.id
        assert mission.approval_required is False
        assert mission.status == "ready"

    await engine.dispose()


@pytest.mark.asyncio
async def test_context_requires_current_membership_and_preserves_explicit_map_context() -> None:
    assert _MODEL_MODULES
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        account = Account(name="Satchy context")
        session.add(account)
        await session.flush()
        org = Organization(
            account_id=account.id,
            name="Context Org",
            slug=f"context-{uuid4().hex[:8]}",
            enabled=True,
        )
        session.add(org)
        await session.flush()
        site = Site(
            organization_id=org.id,
            name="Snowbird",
            slug=f"snowbird-{uuid4().hex[:8]}",
            enabled=True,
        )
        session.add(site)
        user = User(email=f"{uuid4().hex}@example.com", display_name="Operator", enabled=True)
        session.add(user)
        await session.flush()
        session.add(
            Membership(
                organization_id=org.id,
                user_id=user.id,
                role=MembershipRole.OPERATOR,
                enabled=True,
            )
        )
        session.add(
            WorkspacePreference(
                organization_id=org.id,
                user_id=user.id,
                modules=["Map", "Satchy"],
                satchy_preferences={
                    "explicit": {
                        "response_detail": "brief",
                        "preferred_workflows": ["field_observation"],
                    }
                },
            )
        )
        await session.flush()

        active_map = ActiveMapContext(
            map_id="avalanche",
            selected_layers=["slope_angle", "observations"],
            selected_terrain="Cardiff Bowl",
        )
        context = await build_satchy_context(
            session,
            organization_id=org.id,
            site_id=site.id,
            user_id=user.id,
            objective="Review current field observations",
            active_map=active_map,
        )
        assert context.user_id == user.id
        assert context.membership_role == "operator"
        assert context.active_map is not None
        assert context.active_map.selected_terrain == "Cardiff Bowl"
        assert context.user_preferences["explicit"]["response_detail"] == "brief"
        assert context.user_preferences["explicit"]["preferred_workflows"] == [
            "field_observation"
        ]

        outsider = User(
            email=f"{uuid4().hex}@example.com",
            display_name="Outsider",
            enabled=True,
        )
        session.add(outsider)
        await session.flush()
        with pytest.raises(TenantAccessDenied, match="member"):
            await build_satchy_context(
                session,
                organization_id=org.id,
                site_id=site.id,
                user_id=outsider.id,
            )

    await engine.dispose()


@pytest.mark.asyncio
async def test_radio_model_fallback_understands_natural_mission_without_authorizing() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        payload = __import__("json").loads(request.content)
        assert payload["stream"] is False
        assert isinstance(payload["format"], dict)
        assert "approval" in payload["messages"][0]["content"].casefold()
        return httpx.Response(
            200,
            json={
                "message": {
                    "content": (
                        '{"intent":"request_mission","confidence":0.93,'
                        '"references_context":true}'
                    )
                }
            },
        )

    settings = SimpleNamespace(
        intelligence_provider="ollama",
        ollama_base_url="http://ollama.test",
        ollama_model="qwen3:1.7b",
        intelligence_timeout_seconds=5.0,
    )
    resolved = await resolve_radio_intent(
        settings=settings,
        text="Control 2 to Satchy, can you get a look over at Cardiff for us?",
        context={"conversation": {"active_location": "Cardiff Bowl"}},
        transport=httpx.MockTransport(handler),
    )

    assert resolved.intent == SatchyIntent.REQUEST_MISSION
    assert resolved.confidence == 0.93
    assert resolved.explicit is False
    assert resolved.references_context is True


@pytest.mark.asyncio
async def test_explicit_radio_approval_never_uses_model_fallback() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("Explicit approval must never be sent to the model")

    settings = SimpleNamespace(
        intelligence_provider="ollama",
        ollama_base_url="http://ollama.test",
        ollama_model="qwen3:1.7b",
        intelligence_timeout_seconds=5.0,
    )
    resolved = await resolve_radio_intent(
        settings=settings,
        text="Satchy, Control 2. Approve.",
        transport=httpx.MockTransport(handler),
    )

    assert resolved.intent == SatchyIntent.APPROVE_ACTION
    assert resolved.explicit is True
