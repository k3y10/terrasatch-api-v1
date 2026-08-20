from terrasatch.identity.models import TeamMembership
from terrasatch.masterdata.adapters import adapters


def test_team_membership_is_explicit_tenant_scoped_human_access() -> None:
    columns = TeamMembership.__table__.c

    assert TeamMembership.__tablename__ == "team_memberships"
    assert {"organization_id", "user_id", "team_id", "enabled"}.issubset(columns.keys())
    unique_names = {constraint.name for constraint in TeamMembership.__table__.constraints}
    assert "uq_team_memberships_org_user_team" in unique_names


def test_flaik_context_is_an_allow_listed_partner_source_adapter() -> None:
    assert "manual_snapshot" in adapters.keys()
    assert "flaik_context" in adapters.keys()
