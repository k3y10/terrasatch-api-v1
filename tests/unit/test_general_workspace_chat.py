from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from terrasatch.identity.models import MembershipRole
from terrasatch.workspace import routes


@pytest.mark.asyncio
async def test_general_satchy_chat_without_site_cannot_propose_actions(monkeypatch):
    db = AsyncMock()
    db.scalar.return_value = None
    db.get.return_value = None
    db.add_all = MagicMock()
    factory = MagicMock()
    factory.return_value.__aenter__.return_value = db
    monkeypatch.setattr(routes, "create_session_factory", lambda settings: factory)
    monkeypatch.setattr(routes, "csrf", lambda request: None)
    monkeypatch.setattr(
        routes,
        "access",
        AsyncMock(
            return_value=(SimpleNamespace(id=uuid4()), SimpleNamespace(role=MembershipRole.OWNER))
        ),
    )
    monkeypatch.setattr(routes, "writable", AsyncMock())
    monkeypatch.setattr(routes, "enforce_public_rate_limit", AsyncMock())
    answer = AsyncMock(return_value=("Choose workspace panels.", "test-model"))
    monkeypatch.setattr(routes, "answer_workspace", answer)
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(settings=None)))
    result = await routes.chat(uuid4(), routes.Chat(message="Help me choose tools"), request)
    assert result["action_id"] is None and result["approval_required"] is False
    assert answer.call_args.kwargs["context"]["limitations"].startswith("No field site")
    assert db.add_all.call_count == 1
    with pytest.raises(HTTPException) as error:
        await routes.chat(uuid4(), routes.Chat(message="Help", site_id=uuid4()), request)
    assert error.value.status_code == 404
    assert answer.call_count == 1
