"""Workspace email ingestion, visibility, and sending safety."""
# ruff: noqa: E501

from __future__ import annotations

from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from terrasatch.config import Settings
from terrasatch.database.base import Base
from terrasatch.errors import InvalidConfiguration, ResourceNotFound
from terrasatch.identity.models import Account, Membership, MembershipRole, Organization, User
from terrasatch.workspace.email_models import WorkspaceEmailMessage
from terrasatch.workspace.email_service import (
    get_workspace_attachment,
    ingest_resend_received_email,
    list_workspace_emails,
    send_workspace_email,
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
        assert sent_payload["from"] == "ops@terrasatch.com"

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

    await engine.dispose()
