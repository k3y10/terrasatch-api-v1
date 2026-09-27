"""Non-secret setup guidance for the workspace connection manager."""

from .service import _ALLOWED_CONFIGURATION_KEYS

MANUAL_FIELDS = {
    "microsoft_teams": ["webhook_url"],
    "webhook": ["webhook_url", "signing_secret"],
    "aws_s3": ["access_key_id", "secret_access_key", "session_token"],
    "cloudflare_r2": ["access_key_id", "secret_access_key"],
    "snowflake": ["programmatic_access_token"],
    "caltopo": ["credential_id", "credential_secret"],
}
LIST_FIELDS = {"recipients", "collection_ids", "feature_layer_urls", "map_ids", "allowed_imeis"}
NUMBER_FIELDS = {"max_features", "max_items", "max_periods"}


def setup_guidance(item, settings):
    """Explain platform readiness separately from customer authorization."""
    key = item["key"]
    state = item["connect_status"]
    if state == "managed":
        detail = (
            "Managed by TerraSatch."
            if item["runtime_ready"]
            else "TerraSatch platform setup is incomplete."
        )
    elif state == "coming_soon":
        detail = "This adapter is planned and cannot be installed yet."
    elif state == "partner_required":
        detail = "Provider partner approval is required before this adapter can be enabled."
    elif state == "needs_configuration":
        detail = (
            "TerraSatch must enable encrypted credential storage before accounts can connect."
            if not settings.integration_secret_store_is_configured and item["auth"] != "platform"
            else "TerraSatch must configure the provider app before you can authorize your account."
        )
    elif item["connected"]:
        detail = "An authorized connection exists. Review its status or test it below."
    else:
        detail = "The API adapter is ready. Add your account or approved destination."
    return {
        "detail": detail,
        "configuration_fields": [
            {
                "key": field,
                "type": "list"
                if field in LIST_FIELDS
                else "number"
                if field in NUMBER_FIELDS
                else "text",
            }
            for field in sorted(_ALLOWED_CONFIGURATION_KEYS.get(key, set()))
        ],
        "credential_fields": MANUAL_FIELDS.get(key, []),
    }
