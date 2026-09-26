"""Embedded email keeps workspace navigation and existing security boundaries."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from terrasatch.portal import email_routes as routes
from terrasatch.portal.email_ui import render_email_detail, render_email_inbox


def inbox(embedded=False):
    return render_email_inbox(
        organization_id="org",
        organization_name="Team",
        messages=[{"id": "message", "subject": "<unsafe>"}],
        senders=["ops@terrasatch.com"],
        manageable_mailboxes=["ops@terrasatch.com"],
        organization_members=[{"email": "ericka@terrasatch.com"}],
        delegates={"ops@terrasatch.com": [{"email": "ericka@terrasatch.com"}]},
        csrf_token="csrf",
        embedded=embedded,
    )


def test_embedded_navigation_and_all_forms_keep_context():
    html = inbox(True)
    assert "<header>" not in html and "Back to workspace" not in html
    assert "/portal/email/message?organization=org&amp;embedded=1" in html
    assert html.count('name="embedded" value="1"') == 3
    assert html.count('name="csrf_token"') == 3
    assert "&lt;unsafe&gt;" in html
    standalone = inbox()
    assert "<header>" in standalone and "Back to workspace" in standalone
    assert "embedded=1" not in standalone


def test_detail_reply_and_attachment_stay_in_workspace():
    message = SimpleNamespace(
        id=uuid4(),
        direction="inbound",
        text_body="<script>bad</script>",
        attachments=[{"id": "part/id", "filename": "notes.txt"}],
    )
    html = render_email_detail(
        organization_id="org",
        organization_name="Team",
        message=message,
        reply_allowed=True,
        csrf_token="csrf",
        embedded=True,
    )
    assert "<header>" not in html
    assert "/portal/email?organization=org&amp;embedded=1" in html
    assert 'name="embedded" value="1"' in html
    assert 'target="_blank" rel="noopener noreferrer"' in html
    assert "part%2Fid" in html
    assert "&lt;script&gt;bad&lt;/script&gt;" in html


@pytest.mark.asyncio
@pytest.mark.parametrize("detail", [False, True])
async def test_expired_embedded_session_links_to_top_level_login(monkeypatch, detail):
    monkeypatch.setattr(routes, "_email_context", AsyncMock(side_effect=HTTPException(401)))
    if detail:
        response = await routes.portal_email_detail(uuid4(), MagicMock(), embedded=True)
    else:
        response = await routes.portal_email_inbox(MagicMock(), embedded=True)
    assert response.status_code == 401
    assert b'target="_top"' in response.body
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-frame-options"] == "SAMEORIGIN"
    assert response.headers["content-security-policy"] == "frame-ancestors 'self'"


@pytest.mark.asyncio
async def test_inaccessible_explicit_org_does_not_switch_context(monkeypatch):
    user = SimpleNamespace(id=uuid4(), enabled=True)
    session = AsyncMock()
    session.get.return_value = user
    factory = MagicMock()
    factory.return_value.__aenter__.return_value = session
    monkeypatch.setattr(routes, "create_session_factory", lambda settings: factory)
    monkeypatch.setattr(routes, "_enabled", lambda settings: None)
    monkeypatch.setattr(routes, "_require_user", AsyncMock(return_value=user.id))
    monkeypatch.setattr(routes, "is_internal_workspace_user", lambda user: True)
    monkeypatch.setattr(
        routes,
        "list_user_access",
        AsyncMock(return_value=[SimpleNamespace(organization_id=uuid4())]),
    )
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(settings=None)), session={})
    with pytest.raises(HTTPException) as error:
        await routes._email_context(request, str(uuid4()))
    assert error.value.status_code == 403
    assert request.session == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["compose", "reply", "delegate", "delegate_revoke"])
async def test_embedded_post_redirect_preserves_context_and_csrf(monkeypatch, operation):
    organization = uuid4()
    actor = SimpleNamespace(id=uuid4())
    membership = SimpleNamespace(organization_id=organization, role="owner")
    monkeypatch.setattr(routes, "_email_context", AsyncMock(return_value=(actor, membership)))
    csrf = MagicMock()
    monkeypatch.setattr(routes, "_verify_csrf", csrf)
    session = AsyncMock()
    session.scalar.return_value = actor
    factory = MagicMock()
    factory.return_value.__aenter__.return_value = session
    monkeypatch.setattr(routes, "create_session_factory", lambda settings: factory)
    for service in (
        "send_workspace_email",
        "reply_to_workspace_email",
        "set_mailbox_delegate",
        "remove_mailbox_delegate",
    ):
        monkeypatch.setattr(routes, service, AsyncMock())
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(settings=None)))
    kwargs = dict(request=request, organization=str(organization), csrf_token="csrf", embedded=True)
    if operation == "compose":
        kwargs.update(
            sender="ops@terrasatch.com", recipient="test@example.com", subject="test", body="test"
        )
    elif operation == "reply":
        kwargs.update(email_id=uuid4(), body="test")
    else:
        kwargs.update(mailbox="ops@terrasatch.com", delegate_email="ericka@terrasatch.com")
    response = await getattr(routes, f"portal_email_{operation}")(**kwargs)
    assert response.status_code == 303
    assert response.headers["location"].endswith(f"organization={organization}&embedded=1")
    csrf.assert_called_once_with(request, "csrf")
