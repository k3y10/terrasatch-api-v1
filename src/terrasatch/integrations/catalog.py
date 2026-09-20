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

from .provider_config import provider_app_is_configured


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
    support_status: Literal["managed", "supported", "coming_soon"]
    connect_status: Literal[
        "managed",
        "available",
        "needs_configuration",
        "coming_soon",
    ]
    scopes: list[str]
    allowed_scopes: list[str]
    allowed: bool
    can_connect: bool
    requires_admin: bool
    connected: bool
    connected_scopes: list[str]
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
}

_SUPPORTED_PROVIDER_KEYS = {"google_drive", "slack", "esri_arcgis"}


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
        "scopes": ["user", "team", "organization"],
        "capabilities": [],
        "description": "Microsoft productivity and document workflows.",
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
    "snowflake": {
        "key": "snowflake",
        "name": "Snowflake",
        "category": "data",
        "auth": "service_account",
        "setup_status": "planned",
        "scopes": ["organization"],
        "capabilities": [],
        "description": "Organization-scoped data exchange and analytics.",
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
        "auth": "token",
        "setup_status": "planned",
        "scopes": ["user", "team", "organization"],
        "capabilities": [],
        "description": "Map rendering and approved location context.",
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
        "auth": "provider_specific",
        "setup_status": "planned",
        "scopes": ["user", "team", "organization"],
        "capabilities": [],
        "description": "Outdoor mapping and approved operational layers.",
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
        "auth": "provider_specific",
        "setup_status": "planned",
        "scopes": ["user", "team", "organization"],
        "capabilities": [],
        "description": "Approved device, activity, or field data where provider access permits.",
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
) -> Literal["managed", "supported", "coming_soon"]:
    provider = PROVIDERS.get(provider_key)
    if provider is not None and provider["setup_status"] == "managed":
        return "managed"
    if provider_key in _SUPPORTED_PROVIDER_KEYS:
        return "supported"
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
        configured = bool(
            settings is not None
            and support_status == "supported"
            and provider_app_is_configured(settings, provider["key"])
        )

        if support_status == "managed":
            connect_status = "managed"
            setup_status = "managed"
        elif support_status == "coming_soon":
            connect_status = "coming_soon"
            setup_status = "planned"
        elif configured:
            connect_status = "available"
            setup_status = "available"
        else:
            connect_status = "needs_configuration"
            setup_status = "planned"

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
                "can_connect": bool(allowed_scopes) and connect_status == "available",
                "requires_admin": (
                    support_status == "supported"
                    and not allowed_scopes
                    and any(
                        scope in {"team", "organization"}
                        for scope in provider["scopes"]
                    )
                ),
                "connected": bool(visible_connected_scopes),
                "connected_scopes": visible_connected_scopes,
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
