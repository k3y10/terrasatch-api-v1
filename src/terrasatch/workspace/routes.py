"""Member sessions, tenant-scoped field records, Satchy chat and human reviews."""

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.encoders import jsonable_encoder
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
from terrasatch.identity.models import MembershipRole, Site, User
from terrasatch.portal.routes import _clear_portal_auth, _enabled, _require_user, _verify_csrf
from terrasatch.radio.models import OperationalEvent, Transcript, Transmission
from terrasatch.satchy.agent import answer_workspace
from terrasatch.satchy.assets import list_authorized_assets
from terrasatch.satchy.context import build_satchy_context
from terrasatch.satchy.schemas import ActiveMapContext
from terrasatch.workspace.models import WorkspaceMessage, WorkspacePreference

router = APIRouter(prefix="/api/v1/workspace", tags=["workspace"])
STARTER_MODULES = ["Map", "Radio Log", "Observations", "Satchy"]


class ModulePreferences(BaseModel):
    modules: list[Literal["Map", "Radio Log", "Observations", "Workflows", "Satchy"]] = Field(
        max_length=5
    )


@router.post("/organizations/{organization_id}/preferences")
async def save_preferences(organization_id: UUID, payload: ModulePreferences, request: Request):
    csrf(request)
    async with create_session_factory(request.app.state.settings)() as session:
        user, _ = await access(request, session, organization_id)
        # Serialize first-time creation and updates for this member.
        await session.get(User, user.id, with_for_update=True)
        preference = await session.get(WorkspacePreference, (organization_id, user.id))
        if preference is None:
            preference = WorkspacePreference(organization_id=organization_id, user_id=user.id)
            session.add(preference)
        preference.modules = list(dict.fromkeys(payload.modules))
        await session.commit()
        return {"modules": preference.modules}


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
                },
                "subscription": subscription,
                "sites": [{"id": str(s.id), "name": s.name} for s in sites],
                "assets": [
                    {
                        "id": str(asset.id),
                        "site_id": str(asset.site_id) if asset.site_id else None,
                        "name": asset.name,
                        "type": asset.asset_type,
                        "provider": asset.provider,
                        "capabilities": asset.capabilities,
                        "state": asset.state,
                        "location": asset.location,
                    }
                    for asset in asset_rows
                ],
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