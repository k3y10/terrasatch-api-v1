"""ASGI application factory for the official TerraSatch API."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from starlette.middleware.sessions import SessionMiddleware

from terrasatch import __version__
from terrasatch.admin.routes import router as admin_router
from terrasatch.api.control_plane import router as control_plane_router
from terrasatch.api.radio import router as radio_router
from terrasatch.api.realtime import router as realtime_router
from terrasatch.api.schemas import ErrorDetail, ErrorResponse, HealthResponse
from terrasatch.auth.dependencies import Principal, get_principal, require_scope
from terrasatch.auth.scopes import SUPPORTED_API_SCOPES
from terrasatch.brand import SASQUATCH_ASSET_PATH, SASQUATCH_PREVIEW_PATH, apply_public_branding
from terrasatch.config import Settings, get_settings
from terrasatch.edge.api import router as edge_router
from terrasatch.errors import TerraSatchError
from terrasatch.landing_v2 import build_landing_page
from terrasatch.observability.health import check_readiness, liveness
from terrasatch.observability.logging import configure_logging
from terrasatch.observability.quality import api_catalog, build_quality_report, common_errors
from terrasatch.observability.request_id import RequestIdMiddleware

logger = structlog.get_logger(__name__)
_BRAND_LOGO_PATH = Path(__file__).resolve().parent / "static" / "terrasatch-logo.svg"


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the TerraSatch API without performing network work at import time."""

    configured_settings = settings or get_settings()
    configure_logging(
        level=configured_settings.log_level,
        json_output=configured_settings.log_format.lower() == "json",
    )

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        application.state.settings = configured_settings
        logger.info(
            "api.started",
            environment=configured_settings.environment.value,
            deployment=configured_settings.deployment_name,
            version=__version__,
        )
        yield
        logger.info("api.stopped")

    application = FastAPI(
        title="TerraSatch API",
        version=__version__,
        description="Authorized radio traffic transformed into structured field intelligence.",
        docs_url="/docs" if configured_settings.enable_docs else None,
        redoc_url=None,
        lifespan=lifespan,
    )
    application.state.settings = configured_settings
    application.add_middleware(RequestIdMiddleware)
    if configured_settings.admin_is_configured:
        session_secret = configured_settings.admin_session_secret
        assert session_secret is not None
        application.add_middleware(
            SessionMiddleware,
            secret_key=session_secret.get_secret_value(),
            max_age=configured_settings.admin_session_max_age_seconds,
            same_site="lax",
            https_only=configured_settings.is_production,
        )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=configured_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    )

    @application.exception_handler(TerraSatchError)
    async def terrasatch_error_handler(request: Request, error: TerraSatchError) -> JSONResponse:
        response = ErrorResponse(
            error=ErrorDetail(
                code=error.code,
                message=error.message,
                request_id=getattr(request.state, "request_id", "unknown"),
                details=error.details,
            )
        )
        return JSONResponse(status_code=error.status_code, content=response.model_dump(mode="json"))

    @application.get("/assets/terrasatch-logo.svg", include_in_schema=False)
    async def get_brand_logo() -> FileResponse:
        """Serve the vendored TerraSatch brand mark without an external asset dependency."""

        return FileResponse(
            _BRAND_LOGO_PATH,
            media_type="image/svg+xml",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    @application.get("/assets/terralisten-sasquatch.webp", include_in_schema=False)
    async def get_sasquatch_brand_asset() -> FileResponse:
        """Serve Satchy locally for the TerraListen console UI."""

        return FileResponse(
            SASQUATCH_ASSET_PATH,
            media_type="image/webp",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    @application.get("/assets/terralisten-sasquatch.png", include_in_schema=False)
    async def get_sasquatch_preview_asset() -> FileResponse:
        """Serve the PNG Satchy asset for favicons and social link previews."""

        return FileResponse(
            SASQUATCH_PREVIEW_PATH,
            media_type="image/png",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    @application.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def get_landing_page() -> HTMLResponse:
        """Render a branded public status page without exposing internal configuration."""

        html = build_landing_page(
            environment=configured_settings.environment.value,
            deployment=configured_settings.deployment_name,
            version=__version__,
            docs_enabled=configured_settings.enable_docs,
        )
        return HTMLResponse(apply_public_branding(html))

    @application.get("/health", response_model=HealthResponse, tags=["health"])
    @application.get("/health/live", response_model=HealthResponse, tags=["health"])
    async def get_liveness() -> HealthResponse:
        return liveness(configured_settings)

    @application.get("/health/ready", response_model=HealthResponse, tags=["health"])
    async def get_readiness(response: Response) -> HealthResponse:
        report = await check_readiness(configured_settings)
        if report.status == "unhealthy":
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return report

    api_v1 = APIRouter(prefix="/api/v1", tags=["v1"])

    @api_v1.get("/health", response_model=HealthResponse, tags=["health"])
    async def get_api_health(response: Response) -> HealthResponse:
        report = await check_readiness(configured_settings)
        if report.status == "unhealthy":
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return report

    @api_v1.get("/auth/me", tags=["auth"])
    async def get_current_principal(
        principal: Annotated[Principal, Depends(get_principal)],
    ) -> dict[str, object]:
        """Return the credential-derived tenant context for server integrations."""

        return {
            "organization_id": str(principal.organization_id),
            "scopes": sorted(principal.scopes),
        }

    def reference_payload() -> dict[str, object]:
        return {
            "endpoints": [entry.model_dump() for entry in api_catalog()],
            "supported_scopes": sorted(SUPPORTED_API_SCOPES),
            "common_errors": [entry.model_dump() for entry in common_errors()],
        }

    @api_v1.get("/reference", tags=["reference"])
    async def get_api_reference() -> dict[str, object]:
        """Return the implemented endpoint, scope, and error-code catalog."""

        return reference_payload()

    api_v1.include_router(control_plane_router)
    api_v1.include_router(edge_router)
    api_v1.include_router(radio_router)

    @api_v1.get("/admin/quality", tags=["admin"])
    async def get_admin_quality(
        _principal: Annotated[Principal, Depends(require_scope("admin"))],
    ) -> dict[str, object]:
        """Return live platform quality only to an admin-scoped service credential."""

        return (await build_quality_report(configured_settings)).model_dump(mode="json")

    @api_v1.get("/admin/reference", tags=["admin"])
    async def get_admin_reference(
        _principal: Annotated[Principal, Depends(require_scope("admin"))],
    ) -> dict[str, object]:
        """Return the current implemented API, scopes, and error-code catalog."""

        return reference_payload()

    application.include_router(api_v1)
    application.include_router(realtime_router)
    application.include_router(admin_router)
    return application


app = create_app()
