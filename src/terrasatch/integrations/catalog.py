"""Provider catalog for the workspace integration layer.

The catalog is capability metadata, not a claim that every provider is live. OAuth-backed
providers become available only when the server has the required client configuration and an
encrypted credential store.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, TypedDict, cast

if TYPE_CHECKING:
    from terrasatch.config import Settings


class ProviderDefinition(TypedDict):
    key: str
    name: str
    category: str
    auth: str
    setup_status: Literal["managed", "planned", "available"]
    scopes: list[str]
    capabilities: list[str]
    description: str


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
        "auth": "oauth2_or_token",
        "setup_status": "planned",
        "scopes": ["user", "team", "organization"],
        "capabilities": [],
        "description": "Approved map layers, features, and operational GIS context.",
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


def provider_catalog(settings: Settings | None = None) -> list[ProviderDefinition]:
    items: list[ProviderDefinition] = []
    for provider in PROVIDERS.values():
        item = dict(provider)
        if settings is not None:
            if provider["key"] == "google_drive" and settings.google_drive_oauth_is_configured:
                item["setup_status"] = "available"
            elif provider["key"] == "slack" and settings.slack_oauth_is_configured:
                item["setup_status"] = "available"
        items.append(cast(ProviderDefinition, item))
    return items


def provider_status(provider_key: str, settings: Settings) -> str:
    for provider in provider_catalog(settings):
        if provider["key"] == provider_key:
            return provider["setup_status"]
    return "planned"
