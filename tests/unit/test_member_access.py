from terrasatch.identity.access import role_allows
from terrasatch.identity.models import MembershipRole


def test_membership_role_order_is_monotonic() -> None:
    assert role_allows(MembershipRole.OWNER, MembershipRole.ADMIN) is True
    assert role_allows(MembershipRole.ADMIN, MembershipRole.OPERATOR) is True
    assert role_allows(MembershipRole.OPERATOR, MembershipRole.VIEWER) is True
    assert role_allows(MembershipRole.VIEWER, MembershipRole.OPERATOR) is False
