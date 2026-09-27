from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from terrasatch.config import Settings
from terrasatch.database.base import Base
from terrasatch.identity.models import MembershipRole, User
from terrasatch.workspace.email_routes import require_email_organization
from terrasatch.workspace.email_service import (
    BILLING_MAILBOX,
    SATCHY_MAILBOX,
    remove_mailbox_delegate,
    sendable_mailboxes,
    set_mailbox_delegate,
)


def test_email_organization_fails_closed_and_rejects_other_org():
    org = uuid4()
    for settings, target in [
        (Settings(), org),
        (Settings(workspace_email_organization_id=org), uuid4()),
    ]:
        with pytest.raises(HTTPException) as error:
            require_email_organization(settings, target)
        assert error.value.status_code == 403
    require_email_organization(Settings(workspace_email_organization_id=org), org)


@pytest.mark.asyncio
async def test_billing_send_requires_explicit_owner_delegation_and_revokes():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        owner = User(email="keaton@terrasatch.com", display_name="Keaton", enabled=True)
        member = User(email="ericka@terrasatch.com", display_name="Ericka", enabled=True)
        db.add_all([owner, member])
        await db.flush()
        assert BILLING_MAILBOX not in await sendable_mailboxes(
            db, user=member, role=MembershipRole.OPERATOR
        )
        assert SATCHY_MAILBOX not in await sendable_mailboxes(
            db, user=member, role=MembershipRole.OPERATOR
        )
        await set_mailbox_delegate(
            db,
            actor=owner,
            role=MembershipRole.OWNER,
            mailbox=BILLING_MAILBOX,
            delegate=member,
            can_send=True,
        )
        assert BILLING_MAILBOX in await sendable_mailboxes(
            db, user=member, role=MembershipRole.OPERATOR
        )
        await remove_mailbox_delegate(
            db, actor=owner, role=MembershipRole.OWNER, mailbox=BILLING_MAILBOX, delegate=member
        )
        assert BILLING_MAILBOX not in await sendable_mailboxes(
            db, user=member, role=MembershipRole.OPERATOR
        )
    await engine.dispose()
