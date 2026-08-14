"""TerraSatch API router package."""

from terrasatch.api.control_plane import router as control_plane_router
from terrasatch.edge.api import router as edge_router

control_plane_router.include_router(edge_router)
