from types import SimpleNamespace

import pytest

import terrasatch.edge.service as edge_service
import terrasatch.identity.access as member_access
from terrasatch.config import Settings
from terrasatch.errors import ResourceConflict
from terrasatch.identity.models import MembershipRole


def make_settings(*, edge_limit: int = 100, member_limit: int = 250) -> Settings:
    return Settings(
        environment="local",
        deployment_name="capacity-test",
        api_base_url="http://testserver",
        max_edge_devices=edge_limit,
        max_portal_users=member_limit,
    )


@pytest.mark.asyncio
async def test_edge_capacity_allows_below_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_count(_session: object) -> int:
        return 2

    monkeypatch.setattr(edge_service, "count_registered_edges", fake_count)
    await edge_service._ensure_edge_capacity(object(), make_settings(edge_limit=3))


@pytest.mark.asyncio
async def test_edge_capacity_pauses_new_registration_at_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_count(_session: object) -> int:
        return 3

    monkeypatch.setattr(edge_service, "count_registered_edges", fake_count)
    with pytest.raises(ResourceConflict) as captured:
        await edge_service._ensure_edge_capacity(object(), make_settings(edge_limit=3))

    assert captured.value.details == {
        "registered_nodes": 3,
        "max_edge_devices": 3,
    }


@pytest.mark.asyncio
async def test_existing_counted_member_can_be_updated_at_capacity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = SimpleNamespace(
        id="user-id",
        email="field@example.com",
        display_name="Field User",
        password_hash="existing",
        enabled=True,
    )
    membership = SimpleNamespace(role=MembershipRole.VIEWER, enabled=True)
    organization = SimpleNamespace(id="org-id")

    class FakeSession:
        async def get(self, _model: object, _identifier: object) -> object:
            return organization

        async def scalar(self, _statement: object) -> object:
            return user if not hasattr(self, "seen_user") else membership

        async def flush(self) -> None:
            return None

    session = FakeSession()
    session.seen_user = True

    async def fake_count(_session: object) -> int:
        return 1

    async def fake_counted(_session: object, _user: object) -> bool:
        return True

    monkeypatch.setattr(member_access, "count_portal_users", fake_count)
    monkeypatch.setattr(member_access, "_user_counts_toward_capacity", fake_counted)
    monkeypatch.setattr(member_access, "hash_admin_password", lambda _password: "new-hash")

    # The service should not reject an existing active user merely because the
    # unique-user limit has been reached. Password/role maintenance remains available.
    result_user, _ = await member_access.create_or_update_organization_member(
        session,  # type: ignore[arg-type]
        organization_id=organization.id,
        email=user.email,
        display_name="Updated User",
        password="long-enough-password",
        role=MembershipRole.OPERATOR,
        settings=make_settings(member_limit=1),
    )
    assert result_user.display_name == "Updated User"
