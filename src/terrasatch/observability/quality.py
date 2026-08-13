"""Operational quality reporting for API clients and the administrator console."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from terrasatch.api.schemas import (
    ApiCatalogEntry,
    ComponentStatus,
    ErrorCodeReference,
    QualityReport,
)
from terrasatch.config import Settings
from terrasatch.observability.health import check_readiness, check_worker


def api_catalog() -> list[ApiCatalogEntry]:
    """Describe only routes implemented by the current service version."""

    return [
        ApiCatalogEntry(
            method="GET",
            path="/health",
            authorization="public",
            summary="Process liveness without backing-service checks.",
        ),
        ApiCatalogEntry(
            method="GET",
            path="/health/ready",
            authorization="public",
            summary="PostgreSQL and Redis readiness; returns 503 when unavailable.",
        ),
        ApiCatalogEntry(
            method="GET",
            path="/api/v1/health",
            authorization="public",
            summary="Versioned readiness check.",
        ),
        ApiCatalogEntry(
            method="GET",
            path="/api/v1/reference",
            authorization="public",
            summary="Implemented route and error-code reference.",
        ),
        ApiCatalogEntry(
            method="GET",
            path="/api/v1/auth/me",
            authorization="bearer_api_key",
            summary="Credential-derived organization and API scopes.",
        ),
        ApiCatalogEntry(
            method="GET",
            path="/api/v1/sites",
            authorization="bearer_api_key",
            summary="List sites in the credential-derived organization.",
        ),
        ApiCatalogEntry(
            method="POST",
            path="/api/v1/sites",
            authorization="bearer_api_key",
            summary="Create a site in the credential-derived organization.",
        ),
        ApiCatalogEntry(
            method="GET",
            path="/api/v1/agents",
            authorization="bearer_api_key",
            summary="List TerraSatch agents in the authenticated organization.",
        ),
        ApiCatalogEntry(
            method="POST",
            path="/api/v1/agents",
            authorization="bearer_api_key",
            summary="Create a site-scoped TerraSatch processing agent.",
        ),
        ApiCatalogEntry(
            method="GET",
            path="/api/v1/channels",
            authorization="bearer_api_key",
            summary="List logical monitored channels.",
        ),
        ApiCatalogEntry(
            method="POST",
            path="/api/v1/channels",
            authorization="bearer_api_key",
            summary="Create a logical monitored channel.",
        ),
        ApiCatalogEntry(
            method="GET",
            path="/api/v1/callsigns",
            authorization="bearer_api_key",
            summary="List configured callsigns and aliases.",
        ),
        ApiCatalogEntry(
            method="POST",
            path="/api/v1/callsigns",
            authorization="bearer_api_key",
            summary="Create a tenant-owned callsign.",
        ),
        ApiCatalogEntry(
            method="POST",
            path="/api/v1/transmissions",
            authorization="bearer_api_key",
            summary="Ingest authorized text representing one radio transmission.",
        ),
        ApiCatalogEntry(
            method="GET",
            path="/api/v1/transmissions",
            authorization="bearer_api_key",
            summary="List preserved source transmissions.",
        ),
        ApiCatalogEntry(
            method="GET",
            path="/api/v1/transcripts",
            authorization="bearer_api_key",
            summary="List preserved transcripts derived from transmissions.",
        ),
        ApiCatalogEntry(
            method="GET",
            path="/api/v1/events",
            authorization="bearer_api_key",
            summary="List structured operational events linked to source records.",
        ),
        ApiCatalogEntry(
            method="WS",
            path="/ws/v1/events",
            authorization="bearer_api_key",
            summary="Tenant-scoped realtime event subscription; token is sent in the first message.",
        ),
        ApiCatalogEntry(
            method="GET",
            path="/api/v1/api-keys",
            authorization="bearer_api_key",
            summary="List non-secret API-key metadata for the organization.",
        ),
        ApiCatalogEntry(
            method="POST",
            path="/api/v1/api-keys",
            authorization="bearer_api_key",
            summary="Issue a server API key; the raw token is returned once.",
        ),
        ApiCatalogEntry(
            method="POST",
            path="/api/v1/api-keys/{api_key_id}/revoke",
            authorization="bearer_api_key",
            summary="Revoke an API key in the credential-derived organization.",
        ),
        ApiCatalogEntry(
            method="GET",
            path="/api/v1/admin/quality",
            authorization="bearer_api_key",
            summary="Admin-scoped operational quality report.",
        ),
        ApiCatalogEntry(
            method="GET",
            path="/admin",
            authorization="admin_session",
            summary="Browser operator console with controlled create operations.",
        ),
    ]


def common_errors() -> list[ErrorCodeReference]:
    """Return the stable error reference applicable to current API routes."""

    return [
        ErrorCodeReference(
            http_status=400,
            code="invalid_configuration",
            meaning="Configuration or requested resource selection is invalid.",
        ),
        ErrorCodeReference(
            http_status=401,
            code="authentication_required",
            meaning="A bearer API key is absent, invalid, expired, or revoked.",
        ),
        ErrorCodeReference(
            http_status=403,
            code="insufficient_scope",
            meaning="The API key lacks the required scope for this operation.",
        ),
        ErrorCodeReference(
            http_status=422,
            code="validation_error",
            meaning="The request shape or value does not meet the API contract.",
        ),
        ErrorCodeReference(
            http_status=503,
            code="service_unavailable",
            meaning="A required dependency is not ready; retry after remediation.",
        ),
    ]


async def build_quality_report(settings: Settings) -> QualityReport:
    """Build a bounded report without exposing secrets or connection details."""

    readiness, worker = await asyncio.gather(check_readiness(settings), check_worker(settings))
    components: list[ComponentStatus] = [
        ComponentStatus(name="api", status="healthy"),
        *[
            ComponentStatus(name=item.name, status=item.status, detail=item.detail)
            for item in readiness.dependencies
        ],
        worker,
        ComponentStatus(
            name="speech_to_text",
            status="disabled",
            detail=f"{settings.stt_provider} is not activated in the foundation release",
        ),
        ComponentStatus(
            name="intelligence",
            status="disabled" if settings.intelligence_provider != "deterministic" else "healthy",
            detail=(
                f"{settings.intelligence_provider} is not activated in this release"
                if settings.intelligence_provider != "deterministic"
                else "deterministic TerraEngine provider available"
            ),
        ),
    ]
    is_passing = all(item.status == "healthy" for item in components if item.status != "disabled")
    return QualityReport(
        status="pass" if is_passing else "degraded",
        generated_at=datetime.now(UTC),
        components=components,
        endpoints=api_catalog(),
        common_errors=common_errors(),
    )
