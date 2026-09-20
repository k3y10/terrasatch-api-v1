"""Member sessions, tenant-scoped field records, Satchy chat and human reviews."""

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select

from terrasatch.actions.models import SatchyAction
from terrasatch.actions.service import approve_action, reject_action
from terrasatch.admin.security import issue_csrf_token
from terrasatch.billing.rate_limit import enforce_public_rate_limit
from terrasatch.billing.service import get_stripe_customer_id, get_subscription_for_organization
from terrasatch.billing.stripe_gateway import StripeGateway
from terrasatch.database.session import create_session_factory
from terrasatch.edge.models import EdgeDevice
from terrasatch.identity.access import (
    authenticate_user,
    get_user_organization_access,
    list_user_access,
    role_allows,
)
from terrasatch.identity.models import MembershipRole, Site, Team, User
from terrasatch.integrations.catalog import provider_catalog
from terrasatch.integrations.models import IntegrationScope
from terrasatch.integrations.oauth_service import (
    begin_authorization,
    complete_authorization,
    disconnect_connection,
    probe_connection,
    workspace_return_url,
)
from terrasatch.integrations.service import (
    connection_payload,
    create_connection_request,
    list_visible_connections,
)
from terrasatch.portal.routes import _clear_portal_auth, _enabled, _require_user, _verify_csrf
from terrasatch.radio.models import OperationalEvent, Transcript, Transmission
from terrasatch.satchy.adaptation import observe_workspace_context
from terrasatch.satchy.agent import answer_workspace
from terrasatch.satchy.assets import (
    create_field_asset,
    list_authorized_assets,
    list_field_assets,
    update_field_asset,
)
from terrasatch.satchy.context import build_satchy_context
from terrasatch.satchy.schemas import ActiveMapContext, FieldAssetCreate, FieldAssetUpdate
from terrasatch.workspace.models import WorkspaceMessage, WorkspacePreference

router = APIRouter(prefix="/api/v1/workspace", tags=["workspace"])
STARTER_MODULES = ["Map", "Radio Log", "Observations", "Satchy"]


class SatchyPreferenceSettings(BaseModel):
    response_detail: Literal["brief", "balanced", "detailed"] = "brief"
    preferred_workflows: list[str] = Field(default_factory=list, max_length=32)
    preferred_map_layers: list[str] = Field(default_factory=list, max_length=64)


class ModulePreferences(BaseModel):
    modules: list[Literal["Map", "Radio Log", "Observations", "Workflows", "Satchy"]] = Field(
        max_length=5
    )
    satchy: SatchyPreferenceSettings | None = None


@router.post("/organizations/{organization_id}/preferences")
async def save_preferences(organization_id: UUID, payload: ModulePreferences, request: Request):
    csrf(request)
    async with create_session_factory(request.app.state.settings)() as session:
        user, _ = await access(request, session, organization_id)
        # Serialize first-time creation and updates for this member.
        await session.get(User, user.id, with_for_update=True)
        preference = await session.get(WorkspacePreference, (organization_id, user.id))
        if preference is None:
            preference = WorkspacePreference(
                organization_id=organization_id,
                user_id=user.id,
                modules=[],
                satchy_preferences={},
            )
            session.add(preference)
        preference.modules = list(dict.fromkeys(payload.modules))
        if payload.satchy is not None:
            profile = dict(preference.satchy_preferences or {})
            profile["explicit"] = payload.satchy.model_dump(mode="json")
            preference.satchy_preferences = profile
        await session.commit()
        return {
            "modules": preference.modules,
            "satchy": dict(preference.satchy_preferences or {}),
        }


class Login(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1024)


class Chat(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    site_id: UUID | None = None
    transmission_id: UUID | None = None
    objective: str | None = Field(default=None, max_length=2000)
    active_map: ActiveMapContext | None = None


class Observation(BaseModel):
    site_id: UUID
    request_id: UUID
    text: str = Field(min_length=1, max_length=10000)
    latitude: float | None = Field(default=None, ge=-90, le=90, allow_inf_nan=False)
    longitude: float | None = Field(default=None, ge=-180, le=180, allow_inf_nan=False)

    @model_validator(mode="after")
    def coordinate_pair(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Supply both latitude and longitude")
        if not self.text.strip():
            raise ValueError("Observation cannot be blank")
        return self


class Decision(BaseModel):
    decision: Literal["approve", "reject"]
    notes: str = Field(default="", max_length=2000)


class IntegrationRequest(BaseModel):
    provider: str = Field(min_length=2, max_length=100, pattern=r"^[a-z0-9_]+$")
    scope: IntegrationScope
    team_id: UUID | None = None
    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    configuration: dict[str, object] = Field(default_factory=dict)


def csrf(request):
    _verify_csrf(request, request.headers.get("X-CSRF-Token", ""))


async def access(request, session, organization_id):
    user_id = await _require_user(
        request,
        request.app.state.settings,
        session=session,
    )
    user = await session.get(User, user_id)
    if user is None or not user.enabled:
        raise HTTPException(401, "Sign in required")
    membership = await get_user_organization_access(
        session, user_id=user_id, organization_id=organization_id
    )
    return user, membership


async def writable(session, membership):
    if not role_allows(membership.role, MembershipRole.OPERATOR):
        raise HTTPException(403, "Operator access required")
    subscription = await get_subscription_for_organization(
        session, organization_id=membership.organization_id
    )
    if subscription.service_access == "restricted":
        raise HTTPException(403, "Subscription is restricted; existing records remain readable")


@router.get("/session")
async def session_info(request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    _enabled(request.app.state.settings)
    token = issue_csrf_token(request.session)
    if not request.session.get("portal_user_id"):
        return {"user": None, "organizations": [], "csrf_token": token}
    async with create_session_factory(request.app.state.settings)() as session:
        user_id = await _require_user(
            request,
            request.app.state.settings,
            session=session,
        )
        user = await session.get(User, user_id)
        if user is None or not user.enabled:
            _clear_portal_auth(request)
            raise HTTPException(401, "Sign in required")
        memberships = await list_user_access(session, user_id=user_id)
        return {
            "user": {"id": str(user.id), "name": user.display_name, "email": user.email},
            "organizations": [
                {"id": str(m.organization_id), "name": m.organization_name, "role": m.role.value}
                for m in memberships
            ],
            "csrf_token": token,
        }


@router.post("/login")
async def login(payload: Login, request: Request):
    csrf(request)
    await enforce_public_rate_limit(
        request.app.state.settings,
        category="workspace-login",
        identifier=payload.email,
        limit=10,
        window=900,
    )
    await enforce_public_rate_limit(
        request.app.state.settings,
        category="workspace-login-ip",
        identifier=request.client.host if request.client else "unknown",
        limit=30,
        window=900,
    )
    async with create_session_factory(request.app.state.settings)() as session:
        user = await authenticate_user(session, email=payload.email, password=payload.password)
        if user is None:
            raise HTTPException(401, "Email or password is incorrect")
        request.session.clear()
        request.session["portal_user_id"] = str(user.id)
        request.session["portal_credential_version"] = user.credential_version
        return {"csrf_token": issue_csrf_token(request.session)}


@router.post("/logout")
async def logout(request: Request):
    csrf(request)
    request.session.clear()
    return {"signed_out": True}


def _asset_payload(asset) -> dict[str, object]:
    return {
        "id": str(asset.id),
        "site_id": str(asset.site_id) if asset.site_id else None,
        "team_id": str(asset.team_id) if asset.team_id else None,
        "owner_user_id": str(asset.owner_user_id) if asset.owner_user_id else None,
        "controller_edge_device_id": (
            str(asset.controller_edge_device_id) if asset.controller_edge_device_id else None
        ),
        "name": asset.name,
        "type": asset.asset_type,
        "provider": asset.provider,
        "capabilities": list(asset.capabilities or []),
        "state": asset.state,
        "location": dict(asset.location or {}),
        "policy": dict(asset.policy or {}),
        "enabled": asset.enabled,
    }


async def records(session, organization_id):
    rows = (
        await session.execute(
            select(Transmission, Transcript)
            .outerjoin(
                Transcript,
                (Transcript.transmission_id == Transmission.id)
                & (Transcript.organization_id == organization_id),
            )
            .where(Transmission.organization_id == organization_id)
            .order_by(Transmission.received_at.desc())
            .limit(100)
        )
    ).all()
    ids = [t.id for t, _ in rows]
    events = list(
        await session.scalars(
            select(OperationalEvent).where(
                OperationalEvent.organization_id == organization_id,
                OperationalEvent.transmission_id.in_(ids),
            )
        )
    )
    return [
        {
            "id": str(t.id),
            "source": t.source_type,
            "speaker": t.speaker_text,
            "timestamp": t.started_at or t.received_at,
            "original": transcript.raw_text if transcript else None,
            "location": t.rf_metadata.get("reported_location"),
            "interpretations": [
                {
                    "id": str(e.id),
                    "summary": e.summary,
                    "type": e.event_type,
                    "latitude": e.latitude,
                    "longitude": e.longitude,
                    "location": e.location_text,
                    "confidence": e.confidence,
                    "spatial_status": e.spatial_status,
                }
                for e in events
                if e.transmission_id == t.id
            ],
        }
        for t, transcript in rows
    ]


@router.get("/organizations/{organization_id}")
async def workspace(organization_id: UUID, request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    async with create_session_factory(request.app.state.settings)() as session:
        user, membership = await access(request, session, organization_id)
        preference = await session.get(WorkspacePreference, (organization_id, user.id))
        devices = list(
            await session.scalars(
                select(EdgeDevice)
                .where(EdgeDevice.organization_id == organization_id)
                .order_by(EdgeDevice.name)
            )
        )
        subscription = await get_subscription_for_organization(
            session, organization_id=organization_id
        )
        sites = list(
            await session.scalars(
                select(Site).where(
                    Site.organization_id == organization_id,
                    Site.enabled.is_(True),
                )
            )
        )
        teams = list(
            await session.scalars(
                select(Team)
                .where(
                    Team.organization_id == organization_id,
                    Team.enabled.is_(True),
                )
                .order_by(Team.name)
            )
        )
        connections = await list_visible_connections(
            session,
            organization_id=organization_id,
            user_id=user.id,
        )
        actions = await session.scalars(
            select(SatchyAction)
            .where(SatchyAction.organization_id == organization_id)
            .order_by(SatchyAction.created_at.desc())
            .limit(100)
        )
        messages = list(
            await session.scalars(
                select(WorkspaceMessage)
                .where(
                    WorkspaceMessage.organization_id == organization_id,
                    WorkspaceMessage.user_id == user.id,
                )
                .order_by(WorkspaceMessage.created_at.desc())
                .limit(40)
            )
        )
        assets_by_id = {}
        for site in sites:
            site_assets = await list_authorized_assets(
                session,
                organization_id=organization_id,
                site_id=site.id,
                user_id=user.id,
            )
            assets_by_id.update({asset.id: asset for asset in site_assets})
        asset_rows = list(assets_by_id.values())
        return jsonable_encoder(
            {
                "role": membership.role,
                "modules": preference.modules if preference is not None else STARTER_MODULES,
                "satchy_preferences": (
                    dict(preference.satchy_preferences or {}) if preference is not None else {}
                ),
                "integrations": {
                    "devices": [
                        {
                            "id": str(d.id),
                            "name": d.name,
                            "enabled": d.enabled,
                            "last_seen_at": d.last_seen_at,
                            "agent_version": d.agent_version,
                        }
                        for d in devices
                    ],
                    "engine": {
                        "provider": request.app.state.settings.intelligence_provider,
                        "model": request.app.state.settings.ollama_model,
                    },
                    "catalog": provider_catalog(request.app.state.settings),
                    "connections": [connection_payload(connection) for connection in connections],
                },
                "subscription": subscription,
                "sites": [{"id": str(s.id), "name": s.name} for s in sites],
                "teams": [{"id": str(t.id), "name": t.name, "site_id": str(t.site_id) if t.site_id else None} for t in teams],
                "assets": [_asset_payload(asset) for asset in asset_rows],
                "records": await records(session, organization_id),
                "actions": [
                    {
                        "id": str(a.id),
                        "source_id": str(a.source_transmission_id),
                        "type": a.action_type,
                        "reason": a.reason,
                        "message": a.proposed_message,
                        "status": a.status,
                    }
                    for a in actions
                ],
                "messages": [
                    {"id": str(m.id), "role": m.role, "content": m.content}
                    for m in reversed(messages)
                ],
            }
        )


@router.get("/organizations/{organization_id}/integrations/catalog")
async def integration_catalog(organization_id: UUID, request: Request, response: Response):
    """Return provider capabilities without exposing credentials or pretending roadmap adapters are live."""

    response.headers["Cache-Control"] = "no-store"
    async with create_session_factory(request.app.state.settings)() as session:
        await access(request, session, organization_id)
        return provider_catalog(request.app.state.settings)


@router.post(
    "/organizations/{organization_id}/integrations",
    status_code=status.HTTP_201_CREATED,
)
async def request_integration(
    organization_id: UUID,
    payload: IntegrationRequest,
    request: Request,
):
    """Record a safely scoped provider connection request; raw provider secrets are never accepted."""

    csrf(request)
    async with create_session_factory(request.app.state.settings)() as session:
        user, membership = await access(request, session, organization_id)
        await writable(session, membership)
        connection = await create_connection_request(
            session,
            organization_id=organization_id,
            user_id=user.id,
            role=membership.role,
            provider_key=payload.provider,
            scope=payload.scope,
            team_id=payload.team_id,
            display_name=payload.display_name,
            configuration=payload.configuration,
        )
        await session.commit()
        return jsonable_encoder(connection_payload(connection))


@router.post("/organizations/{organization_id}/integrations/{connection_id}/authorize")
async def authorize_integration(organization_id: UUID, connection_id: UUID, request: Request):
    """Start a single-use server-side OAuth flow for a configured provider."""

    csrf(request)
    async with create_session_factory(request.app.state.settings)() as session:
        user, membership = await access(request, session, organization_id)
        await writable(session, membership)
        connection, url, expires_at = await begin_authorization(
            session,
            request.app.state.settings,
            organization_id=organization_id,
            user_id=user.id,
            role=membership.role,
            connection_id=connection_id,
        )
        await session.commit()
        return {"connection": jsonable_encoder(connection_payload(connection)), "url": url, "expires_at": expires_at}


@router.get("/integrations/oauth/{provider}/callback", include_in_schema=False)
async def integration_oauth_callback(
    provider: str,
    request: Request,
    state: str = Query(min_length=16, max_length=256),
    code: str | None = Query(default=None, max_length=4096),
    error: str | None = Query(default=None, max_length=128),
):
    """Consume one OAuth state and immediately redirect away from authorization-code query params."""

    async with create_session_factory(request.app.state.settings)() as session:
        connection, success, reason = await complete_authorization(
            session,
            request.app.state.settings,
            provider=provider,
            state=state,
            code=code,
            provider_error=error,
        )
        await session.commit()
        return RedirectResponse(
            workspace_return_url(
                request.app.state.settings,
                connection=connection,
                success=success,
                reason=reason,
            ),
            status_code=303,
        )


@router.post("/organizations/{organization_id}/integrations/{connection_id}/test")
async def test_integration(organization_id: UUID, connection_id: UUID, request: Request):
    """Verify the live provider credential without returning the credential itself."""

    csrf(request)
    async with create_session_factory(request.app.state.settings)() as session:
        user, membership = await access(request, session, organization_id)
        await writable(session, membership)
        connection = await probe_connection(
            session,
            request.app.state.settings,
            organization_id=organization_id,
            user_id=user.id,
            role=membership.role,
            connection_id=connection_id,
        )
        await session.commit()
        return jsonable_encoder(connection_payload(connection))


@router.post("/organizations/{organization_id}/integrations/{connection_id}/revoke")
async def revoke_integration(organization_id: UUID, connection_id: UUID, request: Request):
    """Revoke provider credentials first, then remove the encrypted local credential."""

    csrf(request)
    async with create_session_factory(request.app.state.settings)() as session:
        user, membership = await access(request, session, organization_id)
        await writable(session, membership)
        connection = await disconnect_connection(
            session,
            request.app.state.settings,
            organization_id=organization_id,
            user_id=user.id,
            role=membership.role,
            connection_id=connection_id,
        )
        await session.commit()
        return jsonable_encoder(connection_payload(connection))


@router.get("/organizations/{organization_id}/assets")
async def asset_inventory(
    organization_id: UUID,
    request: Request,
):
    """Return the complete field-asset inventory to workspace administrators only."""

    async with create_session_factory(request.app.state.settings)() as session:
        _, membership = await access(request, session, organization_id)
        if not role_allows(membership.role, MembershipRole.ADMIN):
            raise HTTPException(403, "Workspace administrator required to list all field assets")
        assets = await list_field_assets(session, organization_id=organization_id)
        return jsonable_encoder([_asset_payload(asset) for asset in assets])


@router.post(
    "/organizations/{organization_id}/assets",
    status_code=status.HTTP_201_CREATED,
)
async def register_asset(
    organization_id: UUID,
    payload: FieldAssetCreate,
    request: Request,
):
    """Register tenant-scoped infrastructure that Satchy may discover by capability."""

    csrf(request)
    async with create_session_factory(request.app.state.settings)() as session:
        _, membership = await access(request, session, organization_id)
        await writable(session, membership)
        if not role_allows(membership.role, MembershipRole.ADMIN):
            raise HTTPException(403, "Workspace administrator required to register field assets")
        asset = await create_field_asset(
            session,
            organization_id=organization_id,
            payload=payload,
        )
        await session.commit()
        return jsonable_encoder(_asset_payload(asset))


@router.patch("/organizations/{organization_id}/assets/{asset_id}")
async def patch_asset(
    organization_id: UUID,
    asset_id: UUID,
    payload: FieldAssetUpdate,
    request: Request,
):
    """Update field-asset scope, capability, state, controller, or execution policy."""

    csrf(request)
    async with create_session_factory(request.app.state.settings)() as session:
        _, membership = await access(request, session, organization_id)
        await writable(session, membership)
        if not role_allows(membership.role, MembershipRole.ADMIN):
            raise HTTPException(403, "Workspace administrator required to update field assets")
        asset = await update_field_asset(
            session,
            organization_id=organization_id,
            asset_id=asset_id,
            payload=payload,
        )
        await session.commit()
        return jsonable_encoder(_asset_payload(asset))


@router.post("/organizations/{organization_id}/actions/{action_id}")
async def review(organization_id: UUID, action_id: UUID, payload: Decision, request: Request):
    csrf(request)
    async with create_session_factory(request.app.state.settings)() as session:
        user, membership = await access(request, session, organization_id)
        await writable(session, membership)
        operation = approve_action if payload.decision == "approve" else reject_action
        action, _ = await operation(
            session,
            organization_id=organization_id,
            action_id=action_id,
            approver_role=membership.role.value,
            approver_user_id=user.id,
            notes=payload.notes,
        )
        await session.commit()
        return {"id": str(action.id), "status": action.status}


@router.post("/organizations/{organization_id}/billing")
async def billing(organization_id: UUID, request: Request):
    csrf(request)
    async with create_session_factory(request.app.state.settings)() as session:
        _, membership = await access(request, session, organization_id)
        if not role_allows(membership.role, MembershipRole.ADMIN):
            raise HTTPException(403, "Billing administrator required")
        customer = await get_stripe_customer_id(session, organization_id=organization_id)
    return {
        "url": await StripeGateway(request.app.state.settings).create_customer_portal(
            stripe_customer_id=customer
        )
    }


@router.post("/organizations/{organization_id}/chat")
async def chat(organization_id: UUID, payload: Chat, request: Request):
    csrf(request)
    settings = request.app.state.settings
    async with create_session_factory(settings)() as session:
        user, membership = await access(request, session, organization_id)
        await writable(session, membership)
        await enforce_public_rate_limit(
            settings, category="satchy-chat", identifier=str(user.id), limit=10
        )
        selected_site = None
        if payload.site_id is not None:
            selected_site = await session.scalar(
                select(Site).where(
                    Site.id == payload.site_id,
                    Site.organization_id == organization_id,
                    Site.enabled.is_(True),
                )
            )
        elif payload.transmission_id is not None:
            source = await session.scalar(
                select(Transmission).where(
                    Transmission.id == payload.transmission_id,
                    Transmission.organization_id == organization_id,
                )
            )
            if source is None:
                raise HTTPException(404, "Transmission not found")
            selected_site = await session.scalar(
                select(Site).where(
                    Site.id == source.site_id,
                    Site.organization_id == organization_id,
                    Site.enabled.is_(True),
                )
            )
        else:
            selected_site = await session.scalar(
                select(Site)
                .where(
                    Site.organization_id == organization_id,
                    Site.enabled.is_(True),
                )
                .order_by(Site.created_at)
                .limit(1)
            )
        if selected_site is None:
            raise HTTPException(404, "No enabled site is available for Satchy context")

        preference = await session.get(
            WorkspacePreference,
            (organization_id, user.id),
        )
        if preference is None:
            preference = WorkspacePreference(
                organization_id=organization_id,
                user_id=user.id,
                modules=list(STARTER_MODULES),
                satchy_preferences={},
            )
            session.add(preference)
            await session.flush()
        observe_workspace_context(
            preference,
            site_id=selected_site.id,
            active_map=payload.active_map,
        )
        await session.flush()

        history = list(
            await session.scalars(
                select(WorkspaceMessage)
                .where(
                    WorkspaceMessage.organization_id == organization_id,
                    WorkspaceMessage.user_id == user.id,
                )
                .order_by(WorkspaceMessage.created_at.desc())
                .limit(12)
            )
        )
        context = await build_satchy_context(
            session,
            organization_id=organization_id,
            site_id=selected_site.id,
            user_id=user.id,
            transmission_id=payload.transmission_id,
            objective=payload.objective,
            active_map=payload.active_map,
        )
        answer, model = await answer_workspace(
            settings=settings,
            context=context,
            message=payload.message,
            history=[
                {"role": item.role, "content": item.content}
                for item in reversed(history)
            ],
        )
        session.add_all(
            [
                WorkspaceMessage(
                    organization_id=organization_id,
                    user_id=user.id,
                    role="user",
                    content=payload.message,
                ),
                WorkspaceMessage(
                    organization_id=organization_id,
                    user_id=user.id,
                    role="assistant",
                    content=answer[:16000],
                    model=model,
                ),
            ]
        )
        await session.commit()
        return {"answer": answer[:16000]}


@router.post("/organizations/{organization_id}/observations")
async def create_observation(organization_id: UUID, payload: Observation, request: Request):
    """Preserve a human field note even before an AI interpretation is available."""
    csrf(request)
    async with create_session_factory(request.app.state.settings)() as session:
        user, membership = await access(request, session, organization_id)
        await writable(session, membership)
        site = await session.scalar(
            select(Site)
            .where(
                Site.id == payload.site_id,
                Site.organization_id == organization_id,
                Site.enabled.is_(True),
            )
            .with_for_update()
        )
        if site is None:
            raise HTTPException(404, "Site not found")
        source_id = f"workspace:{user.id}:{payload.request_id}"
        existing = await session.scalar(
            select(Transmission).where(
                Transmission.organization_id == organization_id,
                Transmission.source_message_id == source_id,
            )
        )
        if existing is not None:
            return {"id": str(existing.id)}
        location = (
            None
            if payload.latitude is None
            else {
                "latitude": payload.latitude,
                "longitude": payload.longitude,
                "provenance": "user_supplied",
            }
        )
        transmission = Transmission(
            id=uuid4(),
            organization_id=organization_id,
            site_id=site.id,
            source_type="workspace_note",
            source_message_id=source_id,
            speaker_text=user.display_name,
            started_at=datetime.now(UTC),
            rf_metadata={"user_id": str(user.id), "reported_location": location},
        )
        session.add(transmission)
        await session.flush()
        session.add(
            Transcript(
                organization_id=organization_id,
                transmission_id=transmission.id,
                raw_text=payload.text,
                normalized_text=" ".join(payload.text.split()),
                provider="human",
            )
        )
        await session.commit()
        return {"id": str(transmission.id)}