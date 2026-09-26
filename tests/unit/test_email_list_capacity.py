"""Inbox projection remains bounded without weakening mailbox visibility."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import event
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from terrasatch.database.base import Base
from terrasatch.identity.models import MembershipRole, User
from terrasatch.workspace.email_models import WorkspaceEmailMessage
from terrasatch.workspace.email_service import list_workspace_emails


@pytest.mark.asyncio
async def test_email_list_projects_summaries_and_keeps_private_mail_private():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    statements = []

    @event.listens_for(engine.sync_engine, "before_execute")
    def capture(_conn, clause, _multiparams, _params, _options):
        statements.append(clause)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            user = User(email="ericka@terrasatch.com", display_name="Ericka", enabled=True)
            session.add(user)
            await session.flush()
            for number, mailbox in enumerate([user.email, "keaton@terrasatch.com"]):
                session.add(
                    WorkspaceEmailMessage(
                        provider_email_id=f"capacity-{number}",
                        direction="inbound",
                        received_for=mailbox,
                        from_address="sender@example.com",
                        to_addresses=[mailbox],
                        subject="Summary test",
                        text_body="Hello  team\n" + "x" * 1_000_000,
                        html_body="<p>" + "z" * 1_000_000 + "</p>",
                        attachments=[{"filename": "one.txt", "metadata": "y" * 10000}],
                        received_at=datetime.now(UTC),
                    )
                )
            await session.commit()
            session.expunge_all()
            rows = await list_workspace_emails(session, user=user, role=MembershipRole.OPERATOR)
            assert len(rows) == 1
            assert rows[0]["mailbox"] == user.email
            assert rows[0]["attachment_count"] == 1
            assert rows[0]["preview"].startswith("Hello team ")
            assert len(rows[0]["preview"]) == 220
            assert not any(
                isinstance(item, WorkspaceEmailMessage) for item in session.identity_map.values()
            )
            query = next(
                item
                for item in statements
                if hasattr(item, "selected_columns")
                and "text_preview" in item.selected_columns.keys()
            )
            assert "html_body" not in query.selected_columns.keys()
            assert "attachments" not in query.selected_columns.keys()
            assert "text_body" not in query.selected_columns.keys()
            sql = str(query.compile(dialect=postgresql.dialect()))
            assert "json_array_length" in sql and "substr(coalesce(" in sql
            params = query.compile(dialect=postgresql.dialect()).params
            assert 1024 in params.values()
    finally:
        await engine.dispose()
