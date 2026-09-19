"""Capability-based field-asset discovery and mission planning."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.actions.models import ActionStatus, ActionType, SatchyAction
from terrasatch.actions.state import transition_action
from terrasatch.edge.models import EdgeCommand, EdgeDevice
from terrasatch.errors import InvalidConfiguration, ResourceConflict, ResourceNotFound, TenantAccessDenied
from terrasatch.identity.models import Membership, Site, Team, User

from .models import FieldAsset, FieldMission
from .schemas import FieldAssetCreate, FieldAssetUpdate


def _normalized_capabilities(values: list[str] | None) -> list[str]:
    return sorted(
        {
            value.strip().casefold()
            for value in (values or [])
            if isinstance(value, str) and value.strip()
        }
    )


async def _asset_site(
    session: AsyncSession,
    *,
    organization_id: UUID,
    site_id: UUID | None,
) -> Site | None:
    if site_id is None:
        return None
    site = await session.scalar(
        select(Site).where(
            Site.id == site_id,
            Site.organization_id == organization_id,
            Site.enabled.is_(True),
        )
    )
    if site is None:
        raise ResourceNotFound("Field asset site was not found in this organization")
    return site


async def _asset_team(
    session: AsyncSession,
    *,
    organization_id: UUID,
    team_id: UUID | None,
) -> Team | None:
    if team_id is None:
        return None
    team = await session.scalar(
        select(Team).where(
            Team.id == team_id,
            Team.organization_id == organization_id,
            Team.enabled.is_(True),
        )
    )
    if team is None:
        raise ResourceNotFound("Field asset team was not found in this organization")
    return team


async def _asset_owner(
    session: AsyncSession,
    *,
    organization_id: UUID,
    user_id: UUID | None,
) -> User | None:
    if user_id is None:
        return None
    membership = await session.scalar(
        select(Membership).where(
            Membership.organization_id == organization_id,
            Membership.user_id == user_id,
            Membership.enabled.is_(True),
        )
    )
    user = await session.get(User, user_id)
    if membership is None or user is None or not user.enabled:
        raise TenantAccessDenied("Field asset owner is not an enabled organization member")
    return user


async def _asset_controller(
    session: AsyncSession,
    *,
    organization_id: UUID,
    device_id: UUID | None,
) -> EdgeDevice | None:
    if device_id is None:
        return None
    device = await session.scalar(
        select(EdgeDevice).where(
            EdgeDevice.id == device_id,
            EdgeDevice.organization_id == organization_id,
            EdgeDevice.enabled.is_(True),
        )
    )
    if device is None:
        raise ResourceNotFound("Field asset Edge controller was not found in this organization")
    return device


async def _validated_asset_scope(
    session: AsyncSession,
    *,
    organization_id: UUID,
    site_id: UUID | None,
    team_id: UUID | None,
    owner_user_id: UUID | None,
    controller_edge_device_id: UUID | None,
) -> tuple[UUID | None, Team | None, User | None, EdgeDevice | None]:
    site = await _asset_site(session, organization_id=organization_id, site_id=site_id)
    team = await _asset_team(session, organization_id=organization_id, team_id=team_id)
    owner = await _asset_owner(
        session,
        organization_id=organization_id,
        user_id=owner_user_id,
    )
    controller = await _asset_controller(
        session,
        organization_id=organization_id,
        device_id=controller_edge_device_id,
    )

    effective_site_id = site.id if site is not None else None
    if team is not None and team.site_id is not None:
        if effective_site_id is not None and team.site_id != effective_site_id:
            raise InvalidConfiguration("Field asset team and site do not match")
        effective_site_id = team.site_id
    if controller is not None:
        if effective_site_id is not None and controller.site_id != effective_site_id:
            raise InvalidConfiguration("Field asset controller and site do not match")
        effective_site_id = controller.site_id

    return effective_site_id, team, owner, controller


async def get_field_asset(
    session: AsyncSession,
    *,
    organization_id: UUID,
    asset_id: UUID,
    for_update: bool = False,
) -> FieldAsset:
    query = select(FieldAsset).where(
        FieldAsset.id == asset_id,
        FieldAsset.organization_id == organization_id,
    )
    if for_update:
        query = query.with_for_update()
    asset = await session.scalar(query)
    if asset is None:
        raise ResourceNotFound("Field asset was not found")
    return asset


async def create_field_asset(
    session: AsyncSession,
    *,
    organization_id: UUID,
    payload: FieldAssetCreate,
) -> FieldAsset:
    """Register infrastructure only after every referenced scope is tenant validated."""

    name = " ".join(payload.name.split())
    existing = await session.scalar(
        select(FieldAsset).where(
            FieldAsset.organization_id == organization_id,
            FieldAsset.name == name,
        )
    )
    if existing is not None:
        raise ResourceConflict(f"Field asset '{name}' already exists")

    effective_site_id, team, owner, controller = await _validated_asset_scope(
        session,
        organization_id=organization_id,
        site_id=payload.site_id,
        team_id=payload.team_id,
        owner_user_id=payload.owner_user_id,
        controller_edge_device_id=payload.controller_edge_device_id,
    )
    asset = FieldAsset(
        organization_id=organization_id,
        site_id=effective_site_id,
        team_id=team.id if team else None,
        owner_user_id=owner.id if owner else None,
        controller_edge_device_id=controller.id if controller else None,
        name=name,
        asset_type=payload.asset_type.strip().casefold(),
        provider=payload.provider.strip(),
        capabilities=_normalized_capabilities(payload.capabilities),
        state=payload.state,
        location=dict(payload.location),
        policy=dict(payload.policy),
        enabled=payload.enabled,
    )
    session.add(asset)
    await session.flush()
    return asset


async def update_field_asset(
    session: AsyncSession,
    *,
    organization_id: UUID,
    asset_id: UUID,
    payload: FieldAssetUpdate,
) -> FieldAsset:
    asset = await get_field_asset(
        session,
        organization_id=organization_id,
        asset_id=asset_id,
        for_update=True,
    )

    site_id = payload.site_id if "site_id" in payload.model_fields_set else asset.site_id
    team_id = payload.team_id if "team_id" in payload.model_fields_set else asset.team_id
    owner_id = (
        payload.owner_user_id
        if "owner_user_id" in payload.model_fields_set
        else asset.owner_user_id
    )
    controller_id = (
        payload.controller_edge_device_id
        if "controller_edge_device_id" in payload.model_fields_set
        else asset.controller_edge_device_id
    )
    effective_site_id, team, owner, controller = await _validated_asset_scope(
        session,
        organization_id=organization_id,
        site_id=site_id,
        team_id=team_id,
        owner_user_id=owner_id,
        controller_edge_device_id=controller_id,
    )

    if payload.name is not None:
        name = " ".join(payload.name.split())
        duplicate = await session.scalar(
            select(FieldAsset).where(
                FieldAsset.organization_id == organization_id,
                FieldAsset.name == name,
                FieldAsset.id != asset.id,
            )
        )
        if duplicate is not None:
            raise ResourceConflict(f"Field asset '{name}' already exists")
        asset.name = name
    if payload.asset_type is not None:
        asset.asset_type = payload.asset_type.strip().casefold()
    if payload.provider is not None:
        asset.provider = payload.provider.strip()
    if payload.capabilities is not None:
        asset.capabilities = _normalized_capabilities(payload.capabilities)
    if payload.state is not None:
        asset.state = payload.state
    if payload.location is not None:
        asset.location = dict(payload.location)
    if payload.policy is not None:
        asset.policy = dict(payload.policy)
    if payload.enabled is not None:
        asset.enabled = payload.enabled

    asset.site_id = effective_site_id
    asset.team_id = team.id if team else None
    asset.owner_user_id = owner.id if owner else None
    asset.controller_edge_device_id = controller.id if controller else None
    await session.flush()
    return asset


async def list_authorized_assets(
    session: AsyncSession,
    *,
    organization_id: UUID,
    site_id: UUID,
    user_id: UUID | None = None,
    team_id: UUID | None = None,
    required_capabilities: set[str] | frozenset[str] | None = None,
) -> list[FieldAsset]:
    query = select(FieldAsset).where(
        FieldAsset.organization_id == organization_id,
        FieldAsset.enabled.is_(True),
        or_(FieldAsset.site_id == site_id, FieldAsset.site_id.is_(None)),
    )
    if user_id is None:
        query = query.where(FieldAsset.owner_user_id.is_(None))
    else:
        query = query.where(
            or_(FieldAsset.owner_user_id.is_(None), FieldAsset.owner_user_id == user_id)
        )
    if team_id is None:
        query = query.where(FieldAsset.team_id.is_(None))
    else:
        query = query.where(or_(FieldAsset.team_id.is_(None), FieldAsset.team_id == team_id))

    items = list(await session.scalars(query.order_by(FieldAsset.name)))
    required = {item.casefold() for item in required_capabilities or set()}
    if not required:
        return items
    return [
        item
        for item in items
        if required <= {capability.casefold() for capability in item.capabilities or []}
    ]


async def select_asset_for_capabilities(
    session: AsyncSession,
    *,
    organization_id: UUID,
    site_id: UUID,
    required_capabilities: set[str] | frozenset[str],
    user_id: UUID | None = None,
    team_id: UUID | None = None,
) -> FieldAsset | None:
    assets = await list_authorized_assets(
        session,
        organization_id=organization_id,
        site_id=site_id,
        user_id=user_id,
        team_id=team_id,
        required_capabilities=required_capabilities,
    )
    available = [item for item in assets if item.state.casefold() == "available"]
    return available[0] if available else None


async def create_mission_plan(
    session: AsyncSession,
    *,
    organization_id: UUID,
    site_id: UUID,
    objective: str,
    mission_type: str,
    required_capabilities: set[str] | frozenset[str],
    target: dict[str, object],
    parameters: dict[str, object] | None = None,
    requested_by_user_id: UUID | None = None,
    requested_by_callsign_id: UUID | None = None,
    team_id: UUID | None = None,
    source_transmission_id: UUID | None = None,
    conversation_id: UUID | None = None,
) -> FieldMission:
    asset = await select_asset_for_capabilities(
        session,
        organization_id=organization_id,
        site_id=site_id,
        user_id=requested_by_user_id,
        team_id=team_id,
        required_capabilities=required_capabilities,
    )
    if asset is None:
        raise ResourceNotFound("No authorized available field asset satisfies this mission")

    policy = dict(asset.policy or {})
    autonomous = {
        str(item).casefold()
        for item in policy.get("autonomous_mission_types", [])
        if isinstance(item, str)
    }
    preauthorized = (
        policy.get("mission_execution_enabled") is True
        and mission_type.casefold() in autonomous
    )
    mission = FieldMission(
        organization_id=organization_id,
        site_id=site_id,
        asset_id=asset.id,
        requested_by_user_id=requested_by_user_id,
        requested_by_callsign_id=requested_by_callsign_id,
        source_transmission_id=source_transmission_id,
        conversation_id=conversation_id,
        objective=" ".join(objective.split()),
        mission_type=mission_type.strip(),
        required_capabilities=sorted(required_capabilities),
        target=target,
        parameters=parameters or {},
        risk_level=str(policy.get("risk_level", "moderate")),
        approval_required=not preauthorized,
        status="ready" if preauthorized else "awaiting_approval",
    )
    session.add(mission)
    await session.flush()

    if not preauthorized and source_transmission_id is not None and conversation_id is not None:
        action = SatchyAction(
            organization_id=organization_id,
            site_id=site_id,
            conversation_id=conversation_id,
            source_transmission_id=source_transmission_id,
            action_type=ActionType.ASSET_MISSION.value,
            risk_level=mission.risk_level,
            reason=f"Field mission requested: {mission.objective}",
            structured_payload={
                "mission_id": str(mission.id),
                "asset_id": str(asset.id),
                "mission_type": mission.mission_type,
            },
            confidence=0.9,
            approval_required=True,
            status=ActionStatus.PROPOSED.value,
            expires_at=datetime.now(UTC) + timedelta(minutes=15),
        )
        session.add(action)
        await session.flush()
        transition_action(action, ActionStatus.AWAITING_APPROVAL)
        mission.action_id = action.id

    await session.flush()
    return mission


async def queue_field_mission(
    session: AsyncSession,
    *,
    organization_id: UUID,
    mission_id: UUID,
) -> tuple[FieldMission, EdgeCommand]:
    mission = await session.scalar(
        select(FieldMission)
        .where(
            FieldMission.id == mission_id,
            FieldMission.organization_id == organization_id,
        )
        .with_for_update()
    )
    if mission is None:
        raise ResourceNotFound("Field mission was not found")
    if mission.edge_command_id is not None:
        command = await session.get(EdgeCommand, mission.edge_command_id)
        if command is None:
            raise RuntimeError("Field mission references a missing Edge command")
        return mission, command

    action: SatchyAction | None = None
    if mission.approval_required:
        if mission.action_id is None:
            raise InvalidConfiguration("Mission requires an approval action")
        action = await session.scalar(
            select(SatchyAction).where(
                SatchyAction.id == mission.action_id,
                SatchyAction.organization_id == organization_id,
            )
        )
        if action is None or ActionStatus(action.status) != ActionStatus.APPROVED:
            raise InvalidConfiguration("Mission action must be explicitly approved before queueing")

    asset = await session.scalar(
        select(FieldAsset).where(
            FieldAsset.id == mission.asset_id,
            FieldAsset.organization_id == organization_id,
            FieldAsset.enabled.is_(True),
        )
    )
    if asset is None or asset.state.casefold() != "available":
        raise InvalidConfiguration("Mission asset is not currently available")
    if asset.controller_edge_device_id is None:
        raise InvalidConfiguration("Mission asset has no Edge controller")

    device = await session.scalar(
        select(EdgeDevice).where(
            EdgeDevice.id == asset.controller_edge_device_id,
            EdgeDevice.organization_id == organization_id,
            EdgeDevice.site_id == mission.site_id,
            EdgeDevice.enabled.is_(True),
        )
    )
    if device is None:
        raise InvalidConfiguration("Mission controller is not available in this site")
    required = {item.casefold() for item in mission.required_capabilities or []}
    reported = {item.casefold() for item in device.capabilities or []}
    if not required <= reported:
        raise InvalidConfiguration("Edge controller does not report required mission capabilities")
    if dict(asset.policy or {}).get("mission_execution_enabled") is not True:
        raise InvalidConfiguration("Asset mission execution is not enabled by policy")

    command = EdgeCommand(
        organization_id=organization_id,
        site_id=mission.site_id,
        edge_device_id=device.id,
        command_type="asset_mission",
        payload={
            "mission_id": str(mission.id),
            "asset_id": str(asset.id),
            "provider": asset.provider,
            "mission_type": mission.mission_type,
            "objective": mission.objective,
            "required_capabilities": mission.required_capabilities,
            "target": mission.target,
            "parameters": mission.parameters,
        },
        priority=50,
        status="queued",
        expires_at=datetime.now(UTC) + timedelta(minutes=15),
    )
    session.add(command)
    await session.flush()
    mission.edge_command_id = command.id
    mission.status = "queued"
    if action is not None and ActionStatus(action.status) == ActionStatus.APPROVED:
        transition_action(action, ActionStatus.QUEUED)
    await session.flush()
    return mission, command