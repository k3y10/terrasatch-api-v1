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
            status="disabled",
            detail=f"{settings.intelligence_provider} is not activated in the foundation release",
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