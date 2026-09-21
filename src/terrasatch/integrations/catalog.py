"""Provider catalog for the workspace integration layer.

The catalog is capability metadata, not a claim that every provider is live. OAuth-backed
providers become available only when the server has the required client configuration and an
encrypted credential store.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Literal, TypedDict, cast

if TYPE_CHECKING:
    from terrasatch.config import Settings

from .provider_config import (
    provider_app_is_configured,
    provider_secret_is_configured,
)


class CapabilityDefinition(TypedDict):
    key: str
    label: str
    access: Literal["read", "write"]


class ProviderDefinition(TypedDict):
    key: str
    name: str
    category: str
    auth: str
    setup_status: Literal["managed", "planned", "available"]
    support_status: Literal[
        "managed",
        "supported",
        "partner_required",
        "coming_soon",
    ]
    connect_status: Literal[
        "managed",
        "available",
        "external_setup_required",
        "needs_configuration",
        "partner_required",
        "coming_soon",
    ]
    scopes: list[str]
    allowed_scopes: list[str]
    allowed: bool
    can_connect: bool
    requires_admin: bool
    connected: bool
    connected_scopes: list[str]
    runtime_ready: bool
    capabilities: list[str]
    capability_details: list[CapabilityDefinition]
    description: str


CAPABILITIES: dict[str, CapabilityDefinition] = {
    "document.create": {
        "key": "document.create",
        "label": "Create reports and files",
        "access": "write",
    },
    "notification.send": {
        "key": "notification.send",
        "label": "Send notifications",
        "access": "write",
    },
    "map.features.query": {
        "key": "map.features.query",
        "label": "Read map features",
        "access": "read",
    },
    "map.style.read": {
        "key": "map.style.read",
        "label": "Read map styles",
        "access": "read",
    },
    "data.query": {
        "key": "data.query",
        "label": "Query connected data",
        "access": "read",
    },
}

_SUPPORTED_PROVIDER_KEYS = {
    "google_drive",
    "slack",
    "esri_arcgis",
    "microsoft_365",
    "microsoft_teams",
    "webhook",
    "cloudflare_r2",
    "aws_s3",
    "email",
    "snowflake",
    "caltopo",
}
_PARTNER_PROVIDER_KEYS = {"garmin"}


PROVIDERS: dict[str, ProviderDefinition] = {
    "terrasatch_edge": {
        "key": "terrasatch_edge",
        "name": "TerraSatch Edge",
        "category": "field",
        "auth": "managed",
        "setup_status": "managed",
        "scopes": ["organization"],
        "capabilities": [],
        "description": "TerraSatch-managed field runtime and device connection.",
    },
    "google_drive": {
        "key": "google_drive",
        "name": "Google Drive",
        "category": "documents",
        "auth": "oauth2",
        "setup_status": "planned",
        "scopes": ["user", "team", "organization"],
        "capabilities": ["document.create"],
        "description": "Per-file Drive access for approved exports and operational files.",
    },
    "microsoft_365": {
        "key": "microsoft_365",
        "name": "Microsoft 365",
        "category": "productivity",
        "auth": "oauth2",
        "setup_status": "planned",
        "scopes": ["user"],
        "capabilities": ["document.create"],
        "description": "Create approved files in the connected member's OneDrive.",
    },
    "slack": {
        "key": "slack",
        "name": "Slack",
        "category": "communications",
        "auth": "oauth2",
        "setup_status": "planned",
        "scopes": ["team", "organization"],
        "capabilities": ["notification.send"],
        "description": (
            "Approved operational notifications to an explicitly selected Slack destination."
        ),
    },
    "microsoft_teams": {
        "key": "microsoft_teams",
        "name": "Microsoft Teams",
        "category": "communications",
        "auth": "webhook_url",
        "setup_status": "planned",
        "scopes": ["team", "organization"],
        "capabilities": ["notification.send"],
        "description": "Approved notifications through a Microsoft Teams Workflows webhook.",
    },
    "webhook": {
        "key": "webhook",
        "name": "Webhook",
        "category": "automation",
        "auth": "webhook_url",
        "setup_status": "planned",
        "scopes": ["team", "organization"],
        "capabilities": ["notification.send"],
        "description": (
            "Signed outbound notifications to an organization-controlled HTTPS endpoint."
        ),
    },
    "email": {
        "key": "email",
        "name": "Email",
        "category": "communications",
        "auth": "platform",
        "setup_status": "planned",
        "scopes": ["team", "organization"],
        "capabilities": ["notification.send"],
        "description": (
            "Approved operational email to administrator-configured recipients."
        ),
    },
    "cloudflare_r2": {
        "key": "cloudflare_r2",
        "name": "Cloudflare R2",
        "category": "storage",
        "auth": "service_account",
        "setup_status": "planned",
        "scopes": ["team", "organization"],
        "capabilities": ["document.create"],
        "description": (
            "Create approved reports and files in an organization-controlled R2 bucket."
        ),
    },
    "aws_s3": {
        "key": "aws_s3",
        "name": "Amazon S3",
        "category": "storage",
        "auth": "service_account",
        "setup_status": "planned",
        "scopes": ["team", "organization"],
        "capabilities": ["document.create"],
        "description": (
            "Create approved reports and files in a standard regional Amazon S3 bucket."
        ),
    },
    "snowflake": {
        "key": "snowflake",
        "name": "Snowflake",
        "category": "data",
        "auth": "service_account",
        "setup_status": "planned",
        "scopes": ["organization"],
        "capabilities": ["data.query"],
        "description": "Read-only SQL queries through an organization Snowflake PAT.",
    },
    "esri_arcgis": {
        "key": "esri_arcgis",
        "name": "Esri ArcGIS",
        "category": "mapping",
        "auth": "oauth2",
        "setup_status": "planned",
        "scopes": ["user", "team", "organization"],
        "capabilities": ["map.features.query"],
        "description": "Read approved ArcGIS Online feature layers through Satchy.",
    },
    "mapbox": {
        "key": "mapbox",
        "name": "Mapbox",
        "category": "mapping",
        "auth": "managed_token",
        "setup_status": "managed",
        "scopes": ["organization"],
        "capabilities": ["map.style.read"],
        "description": "TerraSatch-managed read access to approved Mapbox styles.",
    },
    "onx_backcountry": {
        "key": "onx_backcountry",
        "name": "onX Backcountry",
        "category": "outdoor",
        "auth": "provider_specific",
        "setup_status": "planned",
        "scopes": ["user", "team", "organization"],
        "capabilities": [],
        "description": "Outdoor mapping context where provider access permits.",
    },
    "caltopo": {
        "key": "caltopo",
        "name": "CalTopo",
        "category": "outdoor",
        "auth": "service_account",
        "setup_status": "planned",
        "scopes": ["team", "organization"],
        "capabilities": ["map.features.query"],
        "description": "Read approved Team maps through a CalTopo service account.",
    },
    "gaia_gps": {
        "key": "gaia_gps",
        "name": "Gaia GPS",
        "category": "outdoor",
        "auth": "provider_specific",
        "setup_status": "planned",
        "scopes": ["user", "team", "organization"],
        "capabilities": [],
        "description": "Outdoor map and route context where provider access permits.",
    },
    "garmin": {
        "key": "garmin",
        "name": "Garmin",
        "category": "outdoor",
        "auth": "oauth2_partner",
        "setup_status": "planned",
        "scopes": ["user", "team", "organization"],
        "capabilities": [],
        "description": "Partner-gated Garmin Connect APIs after TerraSatch program approval.",
    },
    "alltrails": {
        "key": "alltrails",
        "name": "AllTrails",
        "category": "outdoor",
        "auth": "provider_specific",
        "setup_status": "planned",
        "scopes": ["user", "team", "organization"],
        "capabilities": [],
        "description": "Outdoor route context where provider access permits.",
    },
}


def provider_support_status(
    provider_key: str,
) -> Literal["managed", "supported", "partner_required", "coming_soon"]:
    provider = PROVIDERS.get(provider_key)
    if provider is not None and provider["setup_status"] == "managed":
        return "managed"
    if provider_key in _SUPPORTED_PROVIDER_KEYS:
        return "supported"
    if provider_key in _PARTNER_PROVIDER_KEYS:
        return "partner_required"
    return "coming_soon"


def provider_catalog(
    settings: Settings | None = None,
    *,
    admin_access: bool = False,
    connected_scopes: Mapping[str, set[str]] | None = None,
) -> list[ProviderDefinition]:
    items: list[ProviderDefinition] = []
    connection_map = connected_scopes or {}

    for provider in PROVIDERS.values():
        item = dict(provider)
        support_status = provider_support_status(provider["key"])
        provider_key = provider["key"]
        auth_type = provider["auth"]
        oauth_configured = bool(
            settings is not None
            and auth_type == "oauth2"
            and provider_app_is_configured(settings, provider_key)
        )
        managed_configured = bool(
            settings is not None
            and provider_key == "mapbox"
            and provider_secret_is_configured(
                settings,
                "mapbox",
                required_fields={"access_token", "username", "style_ids"},
            )
        )
        manual_supported = (
            support_status == "supported"
            and auth_type in {"service_account", "webhook_url"}
        )
        manual_ready = bool(
            manual_supported
            and settings is not None
            and settings.integration_secret_store_is_configured
        )
        platform_supported = support_status == "supported" and auth_type == "platform"
        platform_ready = bool(
            platform_supported
            and settings is not None
            and provider_key == "email"
            and settings.integration_email_is_configured
        )

        if support_status == "managed":
            connect_status = "managed"
            setup_status = "managed"
            runtime_ready = managed_configured or provider_key == "terrasatch_edge"
        elif support_status == "partner_required":
            connect_status = "partner_required"
            setup_status = "planned"
            runtime_ready = False
        elif support_status == "coming_soon":
            connect_status = "coming_soon"
            setup_status = "planned"
            runtime_ready = False
        elif platform_ready:
            connect_status = "available"
            setup_status = "available"
            runtime_ready = True
        elif platform_supported:
            connect_status = "needs_configuration"
            setup_status = "planned"
            runtime_ready = False
        elif manual_ready:
            connect_status = "external_setup_required"
            setup_status = "available"
            runtime_ready = True
        elif manual_supported:
            connect_status = "needs_configuration"
            setup_status = "planned"
            runtime_ready = False
        elif oauth_configured:
            connect_status = "available"
            setup_status = "available"
            runtime_ready = True
        else:
            connect_status = "needs_configuration"
            setup_status = "planned"
            runtime_ready = False

        allowed_scopes = (
            list(provider["scopes"])
            if admin_access
            else [scope for scope in provider["scopes"] if scope == "user"]
        )
        if support_status != "supported":
            allowed_scopes = []

        visible_connected_scopes = sorted(connection_map.get(provider["key"], set()))
        capability_details = [
            CAPABILITIES[capability]
            for capability in provider["capabilities"]
            if capability in CAPABILITIES
        ]

        item.update(
            {
                "setup_status": setup_status,
                "support_status": support_status,
                "connect_status": connect_status,
                "allowed_scopes": allowed_scopes,
                "allowed": bool(allowed_scopes),
                "can_connect": bool(allowed_scopes)
                and connect_status in {"available", "external_setup_required"},
                "requires_admin": (
                    support_status == "supported"
                    and not allowed_scopes
                    and any(
                        scope in {"team", "organization"}
                        for scope in provider["scopes"]
                    )
                ),
                "connected": (
                    bool(visible_connected_scopes)
                    or (support_status == "managed" and runtime_ready)
                ),
                "connected_scopes": (
                    visible_connected_scopes
                    if visible_connected_scopes
                    else ["organization"]
                    if support_status == "managed" and runtime_ready
                    else []
                ),
                "runtime_ready": runtime_ready,
                "capability_details": capability_details,
            }
        )
        items.append(cast(ProviderDefinition, item))
    return items


def provider_status(provider_key: str, settings: Settings) -> str:
    for provider in provider_catalog(settings):
        if provider["key"] == provider_key:
            return provider["setup_status"]
    return "planned"
