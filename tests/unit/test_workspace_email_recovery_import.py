"""Workspace email recovery import behavior."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from terrasatch.database.base import Base
from terrasatch.identity.models import User
from terrasatch.workspace.email_models import WorkspaceEmailMessage, WorkspaceEmailRead
from terrasatch.workspace.email_recovery import import_workspace_email_bundle


@pytest.mark.asyncio
async def test_recovery_import_remaps_user_by_email_and_is_idempotent() -> None:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    staging_user_id = uuid4()
    production_user_id = uuid4()
    parent_old_id = uuid4()
    child_old_id = uuid4()
    now = datetime.now(UTC).isoformat()

    bundle = {
        "version": 1,
        "users": [
            {
                "id": str(staging_user_id),
                "email": "keaton@terrasatch.com",
            }
        ],
        "messages": [
            {
                "id": str(parent_old_id),
                "provider_email_id": "email_recovery_parent",
                "provider_event_id": "event_parent",
                "direction": "inbound",
                "parent_email_id": None,
                "recipient_user_id": str(staging_user_id),
                "internet_message_id": "<parent@example.com>",
                "received_for": "keaton@terrasatch.com",
                "from_address": "sender@example.com",
                "to_addresses": ["keaton@terrasatch.com"],
                "cc_addresses": [],
                "bcc_addresses": [],
                "reply_to": [],
                "subject": "Parent",
                "text_body": "Parent body",
                "html_body": None,
                "headers": {},
                "attachments": [],
                "received_at": now,
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": str(child_old_id),
                "provider_email_id": "email_recovery_child",
                "provider_event_id": "event_child",
                "direction": "outbound",
                "parent_email_id": str(parent_old_id),
                "recipient_user_id": str(staging_user_id),
                "internet_message_id": "<child@example.com>",
                "received_for": "keaton@terrasatch.com",
                "from_address": "keaton@terrasatch.com",
                "to_addresses": ["sender@example.com"],
                "cc_addresses": [],
                "bcc_addresses": [],
                "reply_to": [],
                "subject": "Re: Parent",
                "text_body": "Reply body",
                "html_body": "<p>Reply body</p>",
                "headers": {},
                "attachments": [],
                "received_at": now,
                "created_at": now,
                "updated_at": now,
            },
        ],
        "reads": [
            {
                "email_id": str(parent_old_id),
                "user_id": str(staging_user_id),
                "read_at": now,
            }
        ],
        "delegates": [],
    }

    async with factory() as session:
        session.add(
            User(
                id=production_user_id,
                email="keaton@terrasatch.com",
                display_name="Keaton",
                enabled=True,
            )
        )
        await session.commit()

        first = await import_workspace_email_bundle(
            session,
            payload=bundle,
        )
        await session.commit()

        assert first == {
            "messages_created": 2,
            "messages_skipped": 0,
            "reads_created": 1,
            "reads_skipped": 0,
            "delegates_created": 0,
            "delegates_skipped": 0,
        }

        messages = list(
            await session.scalars(
                select(WorkspaceEmailMessage).order_by(
                    WorkspaceEmailMessage.provider_email_id
                )
            )
        )
        assert len(messages) == 2
        by_provider = {item.provider_email_id: item for item in messages}
        parent = by_provider["email_recovery_parent"]
        child = by_provider["email_recovery_child"]
        assert parent.recipient_user_id == production_user_id
        assert child.recipient_user_id == production_user_id
        assert child.parent_email_id == parent.id

        read = await session.get(
            WorkspaceEmailRead,
            {
                "email_id": parent.id,
                "user_id": production_user_id,
            },
        )
        assert read is not None

        second = await import_workspace_email_bundle(
            session,
            payload=bundle,
        )
        await session.commit()

        assert second["messages_created"] == 0
        assert second["messages_skipped"] == 2
        assert second["reads_created"] == 0
        assert second["reads_skipped"] == 1
        message_count = await session.scalar(
            select(func.count()).select_from(WorkspaceEmailMessage)
        )
        assert message_count == 2

    await engine.dispose()
