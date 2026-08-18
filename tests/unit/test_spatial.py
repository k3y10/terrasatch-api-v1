from terrasatch.intelligence.core import EventType, ExtractedEvent
from terrasatch.intelligence.spatial import ConfiguredSpatialResolver, KnownLocation


def _resolver() -> ConfiguredSpatialResolver:
    return ConfiguredSpatialResolver(
        [
            KnownLocation(
                name="Cardiff Bowl",
                aliases=["Cardiff", "Cardiff Bowl NE"],
                latitude=40.586,
                longitude=-111.651,
                cell_id="UAC-CARDIFF-NE-9800",
                zone_id="central-wasatch",
            )
        ]
    )


def test_trusted_alias_resolves_to_partner_cell() -> None:
    resolution = _resolver().resolve("cardiff bowl ne")
    assert resolution.matched is True
    assert resolution.name == "Cardiff Bowl"
    assert resolution.cell_id == "UAC-CARDIFF-NE-9800"
    assert resolution.zone_id == "central-wasatch"


def test_untrusted_place_never_gets_coordinates() -> None:
    resolution = _resolver().resolve("Some invented ridge")
    assert resolution.matched is False
    assert resolution.latitude is None
    assert resolution.longitude is None
    assert resolution.cell_id is None


def test_ground_event_attaches_spatial_provenance() -> None:
    event = ExtractedEvent(
        event_type=EventType.OBSERVATION,
        summary="Shooting cracks reported.",
        location_text="Cardiff",
        confidence=0.9,
    )
    grounded = _resolver().ground_event(event)
    assert grounded.latitude == 40.586
    assert grounded.longitude == -111.651
    assert grounded.data["spatial"]["cell_id"] == "UAC-CARDIFF-NE-9800"
    assert grounded.data["spatial"]["source"] == "configured_catalog"
