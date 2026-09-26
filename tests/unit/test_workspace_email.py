"""Workspace email ingestion, visibility, and sending safety."""
# ruff: noqa: E501

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from terrasatch.config import Settings
from terrasatch.database.base import Base
from terrasatch.errors import InvalidConfiguration, ResourceNotFound
from terrasatch.identity.models import Account, Membership, MembershipRole, Organization, User
from terrasatch.portal.email_ui import render_email_inbox
from terrasatch.workspace.email_models import WorkspaceEmailMessage
from terrasatch.workspace.email_service import (
    BILLING_MAILBOX,
    LEGAL_MAILBOX,
    OPS_MAILBOX,
    SUPPORT_MAILBOX,
    get_workspace_attachment,
    ingest_resend_received_email,
    list_workspace_emails,
    send_workspace_email,
    sendable_mailboxes,
    set_mailbox_delegate,
    visible_mailboxes,
)


@pytest.mark.asyncio
async def test_resend_received_email_is_persisted_once_and_visible_to_internal_admin() -> None:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        account = Account(name="TerraSatch")
        session.add(account)
        await session.flush()
        organization = Organization(account_id=account.id, name="TerraSatch", slug="terrasatch")
        user = User(email="keaton@terrasatch.com", display_name="Keaton", enabled=True)
        session.add_all([organization, user])
        await session.flush()
        session.add(
            Membership(
                organization_id=organization.id,
                user_id=user.id,
                role=MembershipRole.OWNER,
                enabled=True,
            )
        )
        await session.commit()

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/emails/receiving/email_inbound_1"
            return httpx.Response(
                200,
                json={
                    "id": "email_inbound_1",
                    "created_at": "2026-09-25T22:00:00Z",
                    "received_for": "keaton@terrasatch.com",
                    "from": "Field Partner <partner@example.com>",
                    "to": ["keaton@terrasatch.com"],
                    "subject": "Field test follow-up",
                    "text": "The field test notes are attached.",
                    "html": "<p>The field test notes are attached.</p>",
                    "message_id": "<partner-message-1@example.com>",
                    "attachments": [
                        {
                            "id": "attachment_1",
                            "filename": "notes.txt",
                            "content_type": "text/plain",
                        }
                    ],
                },
            )

        settings = Settings(
            environment="local",
            resend_api_key=SecretStr("re_test"),
        )
        event = {
            "type": "email.received",
            "created_at": "2026-09-25T22:00:01Z",
            "data": {
                "email_id": "email_inbound_1",
                "from": "Field Partner <partner@example.com>",
                "to": ["keaton@terrasatch.com"],
                "subject": "Field test follow-up",
                "message_id": "<partner-message-1@example.com>",
            },
        }
        result = await ingest_resend_received_email(
            session,
            settings,
            event=event,
            webhook_id="msg_inbound_1",
            transport=httpx.MockTransport(handler),
        )
        await session.commit()
        assert result.matched is True
        assert result.duplicate is False

        duplicate = await ingest_resend_received_email(
            session,
            settings,
            event=event,
            webhook_id="msg_inbound_retry",
            transport=httpx.MockTransport(handler),
        )
        assert duplicate.duplicate is True

        messages = await list_workspace_emails(
            session,
            user=user,
            role=MembershipRole.OWNER,
        )
        assert len(messages) == 1
        assert messages[0]["mailbox"] == "keaton@terrasatch.com"
        assert messages[0]["subject"] == "Field test follow-up"

        def attachment_handler(request: httpx.Request) -> httpx.Response:
            assert (
                request.url.path
                == "/emails/receiving/email_inbound_1/attachments/attachment_1"
            )
            return httpx.Response(
                200,
                json={
                    "id": "attachment_1",
                    "filename": "notes.txt",
                    "content_type": "text/plain",
                    "download_url": "https://example.com/signed/notes.txt",
                    "expires_at": "2026-09-26T05:00:00Z",
                },
            )

        attachment = await get_workspace_attachment(
            session,
            settings,
            user=user,
            role=MembershipRole.OWNER,
            email_id=result.email_id,
            attachment_id="attachment_1",
            transport=httpx.MockTransport(attachment_handler),
        )
        assert attachment["filename"] == "notes.txt"
        assert attachment["download_url"] == "https://example.com/signed/notes.txt"

        with pytest.raises(ResourceNotFound):
            await get_workspace_attachment(
                session,
                settings,
                user=user,
                role=MembershipRole.OWNER,
                email_id=result.email_id,
                attachment_id="not-on-this-message",
                transport=httpx.MockTransport(attachment_handler),
            )

    await engine.dispose()


@pytest.mark.asyncio
async def test_workspace_email_sender_cannot_impersonate_another_person() -> None:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        user = User(email="keaton@terrasatch.com", display_name="Keaton", enabled=True)
        session.add(user)
        await session.commit()

        sent_payload: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            sent_payload.update(__import__("json").loads(request.content))
            return httpx.Response(200, json={"id": "email_outbound_1"})

        settings = Settings(environment="local", resend_api_key=SecretStr("re_test"))
        row = await send_workspace_email(
            session,
            settings,
            user=user,
            role=MembershipRole.OWNER,
            sender="ops@terrasatch.com",
            recipients=["partner@example.com"],
            subject="Ops follow-up",
            text="Thanks for the field notes.",
            request_id=uuid4(),
            transport=httpx.MockTransport(handler),
        )
        await session.commit()
        assert row.direction == "outbound"
        assert sent_payload["from"] == "TerraSatch Operations <ops@terrasatch.com>"
        assert "html" in sent_payload
        assert "LISTEN. WATCH. LEARN. ADAPT." in str(sent_payload["text"])
        assert "terrasatch.com" in str(sent_payload["html"])

        with pytest.raises(InvalidConfiguration):
            await send_workspace_email(
                session,
                settings,
                user=user,
                role=MembershipRole.OWNER,
                sender="ericka@terrasatch.com",
                recipients=["partner@example.com"],
                subject="Not allowed",
                text="This should not send.",
                request_id=uuid4(),
                transport=httpx.MockTransport(handler),
            )

        stored = await session.get(WorkspaceEmailMessage, row.id)
        assert stored is not None
        assert stored.html_body is not None
        assert "TerraSatch Operations" in stored.html_body

    await engine.dispose()



@pytest.mark.asyncio
async def test_admin_does_not_get_blanket_access_to_personal_or_legal_mail() -> None:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        admin = User(email="admin@terrasatch.com", display_name="Admin", enabled=True)
        session.add(admin)
        await session.flush()
        now = datetime.now(UTC)
        for index, mailbox in enumerate(
            [
                "admin@terrasatch.com",
                "keaton@terrasatch.com",
                SUPPORT_MAILBOX,
                OPS_MAILBOX,
                BILLING_MAILBOX,
                LEGAL_MAILBOX,
            ]
        ):
            session.add(
                WorkspaceEmailMessage(
                    provider_email_id=f"email_policy_{index}",
                    direction="inbound",
                    received_for=mailbox,
                    from_address="sender@example.com",
                    to_addresses=[mailbox],
                    cc_addresses=[],
                    bcc_addresses=[],
                    reply_to=[],
                    subject=mailbox,
                    text_body="policy test",
                    html_body=None,
                    headers={},
                    attachments=[],
                    received_at=now,
                )
            )
        await session.commit()

        messages = await list_workspace_emails(
            session,
            user=admin,
            role=MembershipRole.ADMIN,
        )
        visible = {str(item["mailbox"]) for item in messages}
        assert "admin@terrasatch.com" in visible
        assert SUPPORT_MAILBOX in visible
        assert OPS_MAILBOX in visible
        assert BILLING_MAILBOX in visible
        assert "keaton@terrasatch.com" not in visible
        assert LEGAL_MAILBOX not in visible

    await engine.dispose()


@pytest.mark.asyncio
async def test_personal_mailbox_delegation_is_explicit_and_can_allow_send() -> None:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        keaton = User(email="keaton@terrasatch.com", display_name="Keaton", enabled=True)
        ericka = User(email="ericka@terrasatch.com", display_name="Ericka", enabled=True)
        session.add_all([keaton, ericka])
        await session.commit()

        await set_mailbox_delegate(
            session,
            actor=keaton,
            role=MembershipRole.OWNER,
            mailbox="keaton@terrasatch.com",
            delegate=ericka,
            can_send=False,
        )
        await session.commit()

        visible = await visible_mailboxes(
            session,
            user=ericka,
            role=MembershipRole.OPERATOR,
        )
        senders = await sendable_mailboxes(
            session,
            user=ericka,
            role=MembershipRole.OPERATOR,
        )
        assert "keaton@terrasatch.com" in visible
        assert "keaton@terrasatch.com" not in senders

        await set_mailbox_delegate(
            session,
            actor=keaton,
            role=MembershipRole.OWNER,
            mailbox="keaton@terrasatch.com",
            delegate=ericka,
            can_send=True,
        )
        await session.commit()
        senders = await sendable_mailboxes(
            session,
            user=ericka,
            role=MembershipRole.OPERATOR,
        )
        assert "keaton@terrasatch.com" in senders

    await engine.dispose()


@pytest.mark.asyncio
async def test_billing_mailbox_is_human_view_only_even_for_owner() -> None:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        owner = User(email="owner@terrasatch.com", display_name="Owner", enabled=True)
        session.add(owner)
        await session.commit()

        visible = await visible_mailboxes(
            session,
            user=owner,
            role=MembershipRole.OWNER,
        )
        senders = await sendable_mailboxes(
            session,
            user=owner,
            role=MembershipRole.OWNER,
        )
        assert BILLING_MAILBOX in visible
        assert BILLING_MAILBOX not in senders

        with pytest.raises(InvalidConfiguration):
            await send_workspace_email(
                session,
                Settings(environment="local", resend_api_key=SecretStr("re_test")),
                user=owner,
                role=MembershipRole.OWNER,
                sender=BILLING_MAILBOX,
                recipients=["customer@example.com"],
                subject="Should not send",
                text="Billing remains automation-owned.",
                request_id=uuid4(),
            )

    await engine.dispose()



def test_email_inbox_renders_mailbox_access_panel() -> None:
    html = render_email_inbox(
        organization_id=str(uuid4()),
        organization_name="TerraSatch",
        messages=[],
        senders=["keaton@terrasatch.com", OPS_MAILBOX],
        manageable_mailboxes=[
            "keaton@terrasatch.com",
            BILLING_MAILBOX,
            LEGAL_MAILBOX,
        ],
        organization_members=[
            {
                "email": "ericka@terrasatch.com",
                "display_name": "Ericka",
            }
        ],
        delegates={
            "keaton@terrasatch.com": [
                {
                    "email": "ericka@terrasatch.com",
                    "can_send": False,
                }
            ],
            BILLING_MAILBOX: [],
            LEGAL_MAILBOX: [],
        },
        csrf_token="csrf-test",
    )

    assert "MAILBOX ACCESS" in html
    assert "keaton@terrasatch.com" in html
    assert "ericka@terrasatch.com" in html
    assert "view only" in html
    assert "Billing access is view-only" in html
    assert "/portal/email/access/delegate" in html
    assert "/portal/email/access/revoke" in html
