"""Provider catalog for the workspace integration layer.

The catalog describes what TerraSatch understands without claiming a provider adapter is live.
Provider-specific OAuth/API implementations can promote setup_status to "available" later.
"""

from __future__ import annotations

from typing import Literal, TypedDict


class ProviderDefinition(TypedDict):
    key: str
    name: str
    category: str
    auth: str
    setup_status: Literal["managed", "planned", "available"]
    scopes: list[str]
    description: str


PROVIDERS: dict[str, ProviderDefinition] = {
    "terrasatch_edge": {
        "key": "terrasatch_edge",
        "name": "TerraSatch Edge",
        "category": "field",
        "auth": "managed",
        "setup_status": "managed",
        "scopes": ["organization"],
        "description": "TerraSatch-managed field runtime and device connection.",
    },
    "google_drive": {
        "key": "google_drive",
        "name": "Google Drive",
        "category": "documents",
        "auth": "oauth2",
        "setup_status": "planned",
        "scopes": ["user", "team", "organization"],
        "description": "Documents, exports, and approved operational files.",
    },
    "microsoft_365": {
        "key": "microsoft_365",
        "name": "Microsoft 365",
        "category": "productivity",
        "auth": "oauth2",
        "setup_status": "planned",
        "scopes": ["user", "team", "organization"],
        "description": "Microsoft productivity and document workflows.",
    },
    "slack": {
        "key": "slack",
        "name": "Slack",
        "category": "communications",
        "auth": "oauth2",
        "setup_status": "planned",
        "scopes": ["team", "organization"],
        "description": "Approved notifications and operational workflow routing.",
    },
    "snowflake": {
        "key": "snowflake",
        "name": "Snowflake",
        "category": "data",
        "auth": "service_account",
        "setup_status": "planned",
        "scopes": ["organization"],
        "description": "Organization-scoped data exchange and analytics.",
    },
    "esri_arcgis": {
        "key": "esri_arcgis",
        "name": "Esri ArcGIS",
        "category": "mapping",
        "auth": "oauth2_or_token",
        "setup_status": "planned",
        "scopes": ["user", "team", "organization"],
        "description": "Approved map layers, features, and operational GIS context.",
    },
    "mapbox": {
        "key": "mapbox",
        "name": "Mapbox",
        "category": "mapping",
        "auth": "token",
        "setup_status": "planned",
        "scopes": ["user", "team", "organization"],
        "description": "Map rendering and approved location context.",
    },
    "onx_backcountry": {
        "key": "onx_backcountry",
        "name": "onX Backcountry",
        "category": "outdoor",
        "auth": "provider_specific",
        "setup_status": "planned",
        "scopes": ["user", "team", "organization"],
        "description": "Outdoor mapping context where provider access permits.",
    },
    "caltopo": {
        "key": "caltopo",
        "name": "CalTopo",
        "category": "outdoor",
        "auth": "provider_specific",
        "setup_status": "planned",
        "scopes": ["user", "team", "organization"],
        "description": "Outdoor mapping and approved operational layers.",
    },
    "gaia_gps": {
        "key": "gaia_gps",
        "name": "Gaia GPS",
        "category": "outdoor",
        "auth": "provider_specific",
        "setup_status": "planned",
        "scopes": ["user", "team", "organization"],
        "description": "Outdoor map and route context where provider access permits.",
    },
    "garmin": {
        "key": "garmin",
        "name": "Garmin",
        "category": "outdoor",
        "auth": "provider_specific",
        "setup_status": "planned",
        "scopes": ["user", "team", "organization"],
        "description": "Approved device, activity, or field data where provider access permits.",
    },
    "alltrails": {
        "key": "alltrails",
        "name": "AllTrails",
        "category": "outdoor",
        "auth": "provider_specific",
        "setup_status": "planned",
        "scopes": ["user", "team", "organization"],
        "description": "Outdoor route context where provider access permits.",
    },
}


def provider_catalog() -> list[ProviderDefinition]:
    return [dict(provider) for provider in PROVIDERS.values()]
