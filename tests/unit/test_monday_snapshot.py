import json

import httpx
import pytest
from pydantic import SecretStr

from terrasatch.config import Settings
from terrasatch.workspace.monday_service import monday_snapshot


@pytest.mark.asyncio
async def test_monday_missing_configuration_is_explicit():
    assert (await monday_snapshot(Settings()))["connected"] is False


@pytest.mark.asyncio
async def test_monday_only_queries_allowlisted_boards_and_marks_partial():
    def handler(request):
        assert str(request.url) == "https://api.monday.com/v2"
        payload = json.loads(request.content)
        assert payload["query"].startswith("query ")
        assert payload["variables"]["ids"] == ["123"]
        return httpx.Response(
            200,
            json={
                "data": {
                    "boards": [
                        {
                            "id": "123",
                            "name": "Test board",
                            "items_page": {"cursor": "next", "items": []},
                        },
                        {
                            "id": "456",
                            "name": "Other board",
                            "items_page": {"cursor": None, "items": []},
                        },
                    ]
                }
            },
        )

    result = await monday_snapshot(
        Settings(workspace_monday_api_token=SecretStr("test"), workspace_monday_board_ids="123"),
        transport=httpx.MockTransport(handler),
    )
    assert len(result["boards"]) == 1 and result["boards"][0]["partial"] is True


@pytest.mark.asyncio
async def test_monday_route_rejects_other_organization_and_non_admin(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, MagicMock
    from uuid import uuid4

    from fastapi import HTTPException, Response

    from terrasatch.identity.models import MembershipRole
    from terrasatch.workspace import routes

    org = uuid4()
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(settings=Settings(workspace_email_organization_id=org))
        )
    )
    with pytest.raises(HTTPException) as wrong_org:
        await routes.monday_board_snapshot(uuid4(), request, Response())
    assert wrong_org.value.status_code == 403
    db = AsyncMock()
    factory = MagicMock()
    factory.return_value.__aenter__.return_value = db
    monkeypatch.setattr(routes, "create_session_factory", lambda settings: factory)
    monkeypatch.setattr(
        routes,
        "access",
        AsyncMock(
            return_value=(SimpleNamespace(id=uuid4()), SimpleNamespace(role=MembershipRole.VIEWER))
        ),
    )
    with pytest.raises(HTTPException) as viewer:
        await routes.monday_board_snapshot(org, request, Response())
    assert viewer.value.status_code == 403
