from sqlalchemy.dialects import postgresql, sqlite

from terrasatch.masterdata.models import DataSource, Observation, Region, TerrainCell


def test_spatial_models_compile_to_postgis_and_local_text() -> None:
    region_type = Region.__table__.c.geometry.type
    cell_type = TerrainCell.__table__.c.geometry.type

    assert str(region_type.compile(dialect=postgresql.dialect())) == "geometry(MULTIPOLYGON,4326)"
    assert str(cell_type.compile(dialect=postgresql.dialect())) == "geometry(POLYGON,4326)"
    assert str(region_type.compile(dialect=sqlite.dialect())) == "TEXT"
    assert str(cell_type.compile(dialect=sqlite.dialect())) == "TEXT"


def test_canonical_models_keep_sources_and_events_distinct() -> None:
    assert DataSource.__tablename__ == "data_sources"
    assert Observation.__tablename__ == "observations"
    assert "operational_event_id" in Observation.__table__.c
    assert "transmission_id" not in Observation.__table__.c
