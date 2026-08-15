"""TerraSatch browser-administration surfaces."""

from terrasatch.admin.edge_routes import router as edge_admin_router
from terrasatch.admin.routes import router as admin_router

admin_router.include_router(edge_admin_router)
