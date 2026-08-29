"""TerraSatch public-brand asset helpers for the API host."""

from __future__ import annotations

from pathlib import Path

_STATIC_DIR = Path(__file__).resolve().parent / "static"

TERRASATCH_LOGO_ASSET_URL = "/assets/terrasatch.png"
TERRASATCH_LOGO_ASSET_PATH = _STATIC_DIR / "terrasatch.png"
SATCHY_ASSET_URL = "/assets/satchy.png"
SATCHY_ASSET_PATH = _STATIC_DIR / "satchy.png"
SATCHY_PUBLIC_URL = "https://api.terrasatch.com/assets/satchy.png"
LEGACY_SASQUATCH_WEBP_PATH = _STATIC_DIR / "terralisten-sasquatch.webp"

# Compatibility aliases for integrations that imported the original names.
SASQUATCH_ASSET_URL = SATCHY_ASSET_URL
SASQUATCH_ASSET_PATH = SATCHY_ASSET_PATH
SASQUATCH_PREVIEW_URL = SATCHY_ASSET_URL
SASQUATCH_PREVIEW_PUBLIC_URL = SATCHY_PUBLIC_URL
SASQUATCH_PREVIEW_PATH = SATCHY_ASSET_PATH

_REMOTE_SASQUATCH_URL = "https://www.terrasatch.com/terralisten-sasquatch.png"
_THEME_META = '  <meta name="theme-color" content="#090d0f">\n'
_SOCIAL_META = f'''  <link rel="icon" type="image/png" href="{SATCHY_ASSET_URL}">
  <link rel="apple-touch-icon" href="{SATCHY_ASSET_URL}">
  <meta property="og:type" content="website">
  <meta property="og:site_name" content="TerraSatch">
  <meta property="og:title" content="TerraSatch · TerraListen Radio Console">
  <meta
    property="og:description"
    content="Provider-aware radio intelligence with Satchy, the TerraListen AI radio agent."
  >
  <meta property="og:url" content="https://api.terrasatch.com/">
  <meta property="og:image" content="{SATCHY_PUBLIC_URL}">
  <meta property="og:image:type" content="image/png">
  <meta property="og:image:width" content="1254">
  <meta property="og:image:height" content="1254">
  <meta property="og:image:alt" content="Satchy, the TerraSatch Sasquatch holding a field radio">
  <meta name="twitter:card" content="summary">
  <meta name="twitter:title" content="TerraSatch · TerraListen Radio Console">
  <meta
    name="twitter:description"
    content="Provider-aware radio intelligence with Satchy, the TerraListen AI radio agent."
  >
  <meta name="twitter:image" content="{SATCHY_PUBLIC_URL}">
'''


def apply_public_branding(html: str) -> str:
    """Replace remote logo dependencies and inject public social/favicon metadata."""

    branded = html.replace(_REMOTE_SASQUATCH_URL, SATCHY_ASSET_URL)
    branded = branded.replace("/assets/terralisten-sasquatch.webp", SATCHY_ASSET_URL)
    if _SOCIAL_META in branded:
        return branded

    if _THEME_META in branded:
        return branded.replace(_THEME_META, _THEME_META + _SOCIAL_META, 1)

    if "</head>" in branded:
        return branded.replace("</head>", _SOCIAL_META + "</head>", 1)

    return branded
