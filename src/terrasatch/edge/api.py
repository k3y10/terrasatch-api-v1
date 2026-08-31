"""HTTP control plane for TerraSatch Edge devices."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from terrasatch.auth.dependencies import Principal, require_scope
from terrasatch.config import Settings
from terrasatch.database.session import create_session_factory
from terrasatch.edge.command_service import (
    acknowledge_command,
    complete_command,
    list_device_commands,
)
from terrasatch.edge.models import EdgeCommand, EdgeDevice
from terrasatch.edge.schemas import (
    DeviceResponse,
    EdgeCommandResponse,
    EdgeCommandResultRequest,
    EdgeDeviceUpdateRequest,
    EdgeHeartbeatRequest,
    EdgeHeartbeatResponse,
    PairingApproveRequest,
    PairingStartRequest,
    PairingStartResponse,
    PairingTokenRequest,
    PairingTokenResponse,
)
from terrasatch.edge.service import (
    approve_pairing,
    claim_pairing,
    get_device_for_api_key,
    heartbeat_device,
    list_devices,
    start_pairing,
    update_device,
)

router = APIRouter(prefix="/edge", tags=["edge"])


async def _run_database[Result](
    settings: Settings,
    operation: Callable[[AsyncSession], Awaitable[Result]],
) -> Result:
    session_factory = create_session_factory(settings)
    async with session_factory() as session:
        try:
            result = await operation(session)
            await session.commit()
            return result
        except Exception:
            await session.rollback()
            raise


def _device_response(device: EdgeDevice) -> DeviceResponse:
    return DeviceResponse(
        id=device.id,
        organization_id=device.organization_id,
        site_id=device.site_id,
        name=device.name,
        hostname=device.hostname,
        platform=device.platform,
        architecture=device.architecture,
        agent_version=device.agent_version,
        hardware_inventory=device.hardware_inventory,
        capabilities=device.capabilities,
        remote_config=device.remote_config,
        telemetry=getattr(device, "telemetry", {}),
        enabled=device.enabled,
        last_seen_at=device.last_seen_at,
        created_at=device.created_at,
        updated_at=device.updated_at,
    )


def _command_response(command: EdgeCommand) -> EdgeCommandResponse:
    return EdgeCommandResponse(
        id=command.id,
        organization_id=command.organization_id,
        site_id=command.site_id,
        edge_device_id=command.edge_device_id,
        command_type=command.command_type,
        payload=command.payload,
        priority=command.priority,
        status=command.status,
        created_at=command.created_at,
        expires_at=command.expires_at,
        acknowledged_at=command.acknowledged_at,
        completed_at=command.completed_at,
    )


@router.post("/pairings", response_model=PairingStartResponse, status_code=status.HTTP_201_CREATED)
async def post_pairing(payload: PairingStartRequest, request: Request) -> PairingStartResponse:
    settings: Settings = request.app.state.settings
    pairing, device_code = await _run_database(
        settings,
        lambda session: start_pairing(session, payload, settings=settings),
    )
    public_base_url = str(settings.api_base_url).rstrip("/")
    return PairingStartResponse(
        pairing_id=pairing.id,
        device_code=device_code,
        user_code=pairing.user_code,
        verification_url=f"{public_base_url}/admin/edge/pair?code={pairing.user_code}",
        expires_at=pairing.expires_at,
    )


@router.post("/pairings/token", response_model=PairingTokenResponse)
async def post_pairing_token(
    payload: PairingTokenRequest,
    request: Request,
) -> PairingTokenResponse:
    pairing_status, device, token = await _run_database(
        request.app.state.settings,
        lambda session: claim_pairing(
            session,
            settings=request.app.state.settings,
            device_code=payload.device_code,
        ),
    )
    return PairingTokenResponse(
        status=pairing_status,
        token=token,
        device=_device_response(device) if device else None,
    )


@router.post("/pairings/{user_code}/approve", status_code=status.HTTP_204_NO_CONTENT)
async def post_pairing_approval(
    user_code: str,
    payload: PairingApproveRequest,
    request: Request,
    principal: Annotated[Principal, Depends(require_scope("write:edge"))],
) -> None:
    await _run_database(
        request.app.state.settings,
        lambda session: approve_pairing(
            session,
            user_code=user_code,
            organization_id=principal.organization_id,
            api_key_id=principal.api_key_id,
            site_id=payload.site_id,
        ),
    )


@router.get("/devices", response_model=list[DeviceResponse])
async def get_devices(
    request: Request,
    principal: Annotated[Principal, Depends(require_scope("read:edge"))],
) -> list[DeviceResponse]:
    devices = await _run_database(
        request.app.state.settings,
        lambda session: list_devices(session, organization_id=principal.organization_id),
    )
    return [_device_response(device) for device in devices]


@router.patch("/devices/{device_id}", response_model=DeviceResponse)
async def patch_device(
    device_id: UUID,
    payload: EdgeDeviceUpdateRequest,
    request: Request,
    principal: Annotated[Principal, Depends(require_scope("write:edge"))],
) -> DeviceResponse:
    device = await _run_database(
        request.app.state.settings,
        lambda session: update_device(
            session,
            organization_id=principal.organization_id,
            device_id=device_id,
            payload=payload,
        ),
    )
    return _device_response(device)


@router.get("/me", response_model=DeviceResponse)
async def get_edge_me(
    request: Request,
    principal: Annotated[Principal, Depends(require_scope("edge:connect"))],
) -> DeviceResponse:
    device = await _run_database(
        request.app.state.settings,
        lambda session: get_device_for_api_key(
            session,
            organization_id=principal.organization_id,
            api_key_id=principal.api_key_id,
        ),
    )
    return _device_response(device)


@router.post("/heartbeat", response_model=EdgeHeartbeatResponse)
async def post_heartbeat(
    payload: EdgeHeartbeatRequest,
    request: Request,
    principal: Annotated[Principal, Depends(require_scope("edge:connect"))],
) -> EdgeHeartbeatResponse:
    device = await _run_database(
        request.app.state.settings,
        lambda session: heartbeat_device(
            session,
            organization_id=principal.organization_id,
            api_key_id=principal.api_key_id,
            payload=payload,
        ),
    )
    return EdgeHeartbeatResponse(device=_device_response(device), server_time=datetime.now(UTC))


@router.get("/config", response_model=dict[str, object])
async def get_edge_config(
    request: Request,
    principal: Annotated[Principal, Depends(require_scope("edge:connect"))],
) -> dict[str, object]:
    device = await _run_database(
        request.app.state.settings,
        lambda session: get_device_for_api_key(
            session,
            organization_id=principal.organization_id,
            api_key_id=principal.api_key_id,
        ),
    )
    return device.remote_config


@router.get("/commands", response_model=list[EdgeCommandResponse])
async def get_edge_commands(
    request: Request,
    principal: Annotated[Principal, Depends(require_scope("edge:connect"))],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[EdgeCommandResponse]:
    commands = await _run_database(
        request.app.state.settings,
        lambda session: list_device_commands(
            session,
            organization_id=principal.organization_id,
            api_key_id=principal.api_key_id,
            limit=limit,
        ),
    )
    return [_command_response(command) for command in commands]


@router.post("/commands/{command_id}/ack", response_model=EdgeCommandResponse)
async def post_edge_command_ack(
    command_id: UUID,
    request: Request,
    principal: Annotated[Principal, Depends(require_scope("edge:connect"))],
) -> EdgeCommandResponse:
    command = await _run_database(
        request.app.state.settings,
        lambda session: acknowledge_command(
            session,
            organization_id=principal.organization_id,
            api_key_id=principal.api_key_id,
            command_id=command_id,
        ),
    )
    return _command_response(command)


@router.post("/commands/{command_id}/result", response_model=EdgeCommandResponse)
async def post_edge_command_result(
    command_id: UUID,
    payload: EdgeCommandResultRequest,
    request: Request,
    principal: Annotated[Principal, Depends(require_scope("edge:connect"))],
) -> EdgeCommandResponse:
    command = await _run_database(
        request.app.state.settings,
        lambda session: complete_command(
            session,
            organization_id=principal.organization_id,
            api_key_id=principal.api_key_id,
            command_id=command_id,
            result=payload.status,
            detail=payload.detail,
        ),
    )
    return _command_response(command)
