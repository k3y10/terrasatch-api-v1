from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from terrasatch.portal import routes


@pytest.mark.asyncio
async def test_api_session_refreshes_portal_identity_from_validated_account(monkeypatch):
    user_id = uuid4()
    request = SimpleNamespace(
        session={
            "portal_user_id": str(user_id),
            "portal_credential_version": 2,
            "portal_email": "old@example.com",
        }
    )
    settings = SimpleNamespace(admin_session_secret="configured")
    validated = SimpleNamespace(email="ericka@terrasatch.com", display_name="Ericka")
    monkeypatch.setattr(routes, "validate_browser_session", AsyncMock(return_value=validated))
    assert await routes._require_user(request, settings, session=object()) == user_id
    assert request.session["portal_email"] == "ericka@terrasatch.com"
    assert request.session["portal_display_name"] == "Ericka"


@pytest.mark.asyncio
async def test_dashboard_rejects_unavailable_explicit_organization(monkeypatch):
    settings = SimpleNamespace(admin_session_secret="configured")
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(settings=settings)), session={}
    )
    monkeypatch.setattr(routes, "_require_user", AsyncMock(return_value=uuid4()))
    monkeypatch.setattr(
        routes,
        "_run_database",
        AsyncMock(
            return_value=[
                SimpleNamespace(organization_id=uuid4()),
            ]
        ),
    )
    with pytest.raises(HTTPException) as error:
        await routes.portal_dashboard(request, organization=str(uuid4()))
    assert error.value.status_code == 403
    assert "portal_organization" not in request.session
