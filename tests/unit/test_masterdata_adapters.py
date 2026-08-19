import pytest

from terrasatch.masterdata.adapters import AdapterRegistry, ManualSnapshotAdapter


@pytest.mark.asyncio
async def test_manual_adapter_is_bounded_and_network_free() -> None:
    adapter = ManualSnapshotAdapter()

    batch = await adapter.fetch(
        configuration={},
        cursor="cursor-1",
        etag=None,
        last_modified=None,
    )

    assert batch.records == ()
    assert batch.next_cursor == "cursor-1"


def test_adapter_registry_rejects_duplicates_and_unknown_keys() -> None:
    registry = AdapterRegistry()
    registry.register(ManualSnapshotAdapter())

    assert registry.keys() == ("manual_snapshot",)
    assert registry.get("MANUAL_SNAPSHOT").version == "1"
    with pytest.raises(ValueError, match="already registered"):
        registry.register(ManualSnapshotAdapter())
    with pytest.raises(KeyError, match="not registered"):
        registry.get("uac")
