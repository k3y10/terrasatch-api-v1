"""Small PostGIS geometry type without adding a runtime GIS dependency.

PostgreSQL receives a native PostGIS ``geometry`` column. SQLite compiles the
same model field to text so local model and service tests do not need SpatiaLite.
Geometry values are expected to be authoritative WKT/EWKT supplied by an
adapter or reviewed administrator; this module never invents coordinates.
"""

from __future__ import annotations

from sqlalchemy.ext.compiler import compiles
from sqlalchemy.types import UserDefinedType


class Geometry(UserDefinedType):
    """Represent a PostGIS geometry with an explicit type and SRID."""

    cache_ok = True

    def __init__(self, geometry_type: str = "GEOMETRY", srid: int = 4326) -> None:
        self.geometry_type = geometry_type.upper()
        self.srid = srid

    def get_col_spec(self, **_kwargs: object) -> str:
        return f"geometry({self.geometry_type},{self.srid})"


@compiles(Geometry, "sqlite")
def _compile_geometry_sqlite(_type: Geometry, _compiler: object, **_kwargs: object) -> str:
    return "TEXT"
