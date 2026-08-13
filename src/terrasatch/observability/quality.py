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
    """Describe routes implemented by the current service version."""

    entries = [
        ("GET", "/health", "public", "Process liveness without backing-service checks."),
        ("GET", "/health/ready", "public", "PostgreSQL and Redis readiness; returns 503 when unavailable."),
        ("GET", "/api/v1/health", "public", "Versioned readiness check."),
        ("GET", "/api/v1/reference", "public", "Implemented route and error-code reference."),
        ("GET", "/api/v1/auth/me", "bearer_api_key", "Credential-derived organization and API scopes."),
        ("GET", "/api/v1/sites", "bearer_api_key", "List tenant sites with optional enabled filtering."),
        ("POST", "/api/v1/sites", "bearer_api_key", "Create a tenant site."),
        ("GET", "/api/v1/sites/{site_id}", "bearer_api_key", "Read one tenant site."),
        ("PATCH", "/api/v1/sites/{site_id}", "bearer_api_key", "Rename, enable, or disable one tenant site."),
        ("GET", "/api/v1/teams", "bearer_api_key", "List teams with optional site/enabled filtering."),
        ("POST", "/api/v1/teams", "bearer_api_key", "Create a tenant-owned operating team."),
        ("GET", "/api/v1/teams/{team_id}", "bearer_api_key", "Read one tenant-owned operating team."),
        ("PATCH", "/api/v1/teams/{team_id}", "bearer_api_key", "Update or disable a tenant-owned operating team."),
        ("GET", "/api/v1/agents", "bearer_api_key", "List TerraSatch agents with site/profile/enabled filters."),
        ("POST", "/api/v1/agents", "bearer_api_key", "Create a site-scoped TerraSatch processing agent."),
        ("GET", "/api/v1/agents/{agent_id}", "bearer_api_key", "Read one TerraSatch processing agent."),
        ("PATCH", "/api/v1/agents/{agent_id}", "bearer_api_key", "Update or disable one TerraSatch processing agent."),
        ("GET", "/api/v1/channels", "bearer_api_key", "List logical monitored channels with filters."),
        ("POST", "/api/v1/channels", "bearer_api_key", "Create a logical monitored channel."),
        ("GET", "/api/v1/channels/{channel_id}", "bearer_api_key", "Read one logical monitored channel."),
        ("PATCH", "/api/v1/channels/{channel_id}", "bearer_api_key", "Update, reassign, or disable a logical channel."),
        ("GET", "/api/v1/callsigns", "bearer_api_key", "List configured callsigns and aliases with filters."),
        ("POST", "/api/v1/callsigns", "bearer_api_key", "Create a tenant-owned callsign."),
        ("GET", "/api/v1/callsigns/{callsign_id}", "bearer_api_key", "Read one tenant-owned callsign."),
        ("PATCH", "/api/v1/callsigns/{callsign_id}", "bearer_api_key", "Update bindings, aliases, or enabled state for a callsign."),
        ("POST", "/api/v1/transmissions", "bearer_api_key", "Ingest authorized text representing one radio transmission."),
        ("GET", "/api/v1/transmissions", "bearer_api_key", "List preserved source transmissions with source/site/channel filters."),
        ("GET", "/api/v1/transmissions/{transmission_id}", "bearer_api_key", "Read one preserved source transmission."),
        ("GET", "/api/v1/transcripts", "bearer_api_key", "List preserved transcripts, optionally by transmission."),
        ("GET", "/api/v1/transcripts/{transcript_id}", "bearer_api_key", "Read one preserved transcript."),
        ("GET", "/api/v1/events", "bearer_api_key", "List structured events with site/type/callsign/source filters."),
        ("GET", "/api/v1/events/{event_id}", "bearer_api_key", "Read one structured event with source provenance."),
        ("WS", "/ws/v1/events", "bearer_api_key", "Tenant-scoped realtime subscriptions; token is sent in the first message."),
        ("GET", "/api/v1/api-keys", "bearer_api_key", "List non-secret API-key metadata for the organization."),
        ("POST", "/api/v1/api-keys", "bearer_api_key", "Issue a server API key; the raw token is returned once."),
        ("POST", "/api/v1/api-keys/{api_key_id}/revoke", "bearer_api_key", "Revoke an API key in the credential-derived organization."),
        ("GET", "/api/v1/admin/quality", "bearer_api_key", "Admin-scoped operational quality report."),
        ("GET", "/api/v1/admin/reference", "bearer_api_key", "Admin-scoped API and error catalog."),
        ("GET", "/admin", "admin_session", "Browser operator console with controlled create operations."),
    ]
    return [
        ApiCatalogEntry(method=method, path=path, authorization=authorization, summary=summary)
        for method, path, authorization, summary in entries
    ]


def common_errors() -> list[ErrorCodeReference]:
    """Return the stable error reference applicable to current API routes."""

    return [
        ErrorCodeReference(
            http_status=400,
            code="invalid_configuration",
            meaning="Configuration or a requested resource relationship is invalid.",
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
            http_status=404,
            code="not_found",
            meaning="The requested tenant-owned resource does not exist or is not visible to this tenant.",
        ),
        ErrorCodeReference(
            http_status=409,
            code="resource_conflict",
            meaning="A resource with the requested unique name or slug already exists.",
        ),
        ErrorCodeReference(
            http_status=422,
            code="validation_error",
            meaning="The request shape or value does not meet the API contract.",
        ),
        ErrorCodeReference(
            http_status=503,
            code="service_unavailable",
            meaning="A required dependency or configured provider is not ready.",
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
            detail=f"{settings.stt_provider} is not activated in the software-ingest release",
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
