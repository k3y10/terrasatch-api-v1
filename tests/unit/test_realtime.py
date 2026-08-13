from uuid import uuid4

from terrasatch.api.realtime import _authorized_topics
from terrasatch.auth.dependencies import Principal


def principal(*scopes: str) -> Principal:
    return Principal(
        organization_id=uuid4(),
        api_key_id=uuid4(),
        scopes=frozenset(scopes),
    )


def test_admin_can_subscribe_to_all_supported_topics() -> None:
    topics = _authorized_topics(
        principal("admin"),
        ["events", "transmissions", "transcripts", "unknown"],
    )

    assert topics == {"events", "transmissions", "transcripts"}


def test_scoped_key_only_receives_permitted_topics() -> None:
    topics = _authorized_topics(
        principal("read:events"),
        ["events", "transmissions", "transcripts"],
    )

    assert topics == {"events"}
