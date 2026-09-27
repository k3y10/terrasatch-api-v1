from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from terrasatch.config import Settings
from terrasatch.identity.models import MembershipRole
from terrasatch.integrations.catalog import provider_catalog
from terrasatch.integrations.setup import setup_guidance
from terrasatch.workspace import routes


def test_setup_distinguishes_adapter_from_platform_readiness():
    settings = Settings()
    catalog = {x["key"]: x for x in provider_catalog(settings, admin_access=True)}
    assert "encrypted credential storage" in setup_guidance(catalog["slack"], settings)["detail"]
    assert catalog["nws_forecast"]["can_connect"]
    assert "Add your account" in setup_guidance(catalog["nws_forecast"], settings)["detail"]
    assert not catalog["alltrails"]["can_connect"]
    assert "cannot be installed" in setup_guidance(catalog["alltrails"], settings)["detail"]


@pytest.mark.asyncio
async def test_team_setup_requires_owner_and_correct_organization(monkeypatch):
    org = uuid4()
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(settings=SimpleNamespace(workspace_email_organization_id=org))
        )
    )
    for role, target in [(MembershipRole.ADMIN, org), (MembershipRole.OWNER, uuid4())]:
        monkeypatch.setattr(
            routes, "access", AsyncMock(return_value=(object(), SimpleNamespace(role=role)))
        )
        with pytest.raises(HTTPException) as error:
            await routes._team_owner(request, object(), target)
        assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_team_setup_never_resets_existing_identity(monkeypatch):
    db = AsyncMock()
    db.scalar.return_value = object()
    factory = MagicMock()
    factory.return_value.__aenter__.return_value = db
    monkeypatch.setattr(routes, "create_session_factory", lambda settings: factory)
    monkeypatch.setattr(routes, "csrf", lambda request: None)
    monkeypatch.setattr(routes, "_team_owner", AsyncMock(return_value=(object(), object())))
    monkeypatch.setattr(routes, "writable", AsyncMock())
    create = AsyncMock()
    monkeypatch.setattr(routes, "create_or_update_organization_member", create)
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(settings=object())))
    payload = routes.NewTeamMember(
        email="ericka@terrasatch.com", display_name="Ericka", password="test-only-password"
    )
    with pytest.raises(HTTPException) as error:
        await routes.create_team_member(uuid4(), payload, request)
    assert error.value.status_code == 409
    create.assert_not_awaited()
    db.commit.assert_not_awaited()
