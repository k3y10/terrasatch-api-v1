"""TerraSatch public-brand asset helpers for the API host."""

from __future__ import annotations

from pathlib import Path

SASQUATCH_ASSET_URL = "/assets/terralisten-sasquatch.webp"
SASQUATCH_ASSET_PUBLIC_URL = (
    "https://api.terrasatch.com/assets/terralisten-sasquatch.webp"
)
SASQUATCH_ASSET_PATH = (
    Path(__file__).resolve().parent / "static" / "terralisten-sasquatch.webp"
)

_REMOTE_SASQUATCH_URL = "https://www.terrasatch.com/terralisten-sasquatch.png"
_THEME_META = '  <meta name="theme-color" content="#090d0f">\n'
_SOCIAL_META = f'''  <link rel="icon" type="image/webp" href="{SASQUATCH_ASSET_URL}">
  <link rel="apple-touch-icon" href="{SASQUATCH_ASSET_URL}">
  <meta property="og:type" content="website">
  <meta property="og:site_name" content="TerraSatch">
  <meta property="og:title" content="TerraSatch · TerraListen Radio Console">
  <meta
    property="og:description"
    content="Receive-only radio intelligence for field operations."
  >
  <meta property="og:url" content="https://api.terrasatch.com/">
  <meta property="og:image" content="{SASQUATCH_ASSET_PUBLIC_URL}">
  <meta property="og:image:type" content="image/webp">
  <meta property="og:image:width" content="256">
  <meta property="og:image:height" content="256">
  <meta
    property="og:image:alt"
    content="Sassy, the TerraSatch Sasquatch holding a field radio"
  >
  <meta name="twitter:card" content="summary">
  <meta name="twitter:title" content="TerraSatch · TerraListen Radio Console">
  <meta
    name="twitter:description"
    content="Receive-only radio intelligence for field operations."
  >
  <meta name="twitter:image" content="{SASQUATCH_ASSET_PUBLIC_URL}">
'''


def apply_public_branding(html: str) -> str:
    """Replace the remote logo dependency and add explicit link-preview metadata."""

    branded = html.replace(_REMOTE_SASQUATCH_URL, SASQUATCH_ASSET_URL)
    if _SOCIAL_META not in branded and _THEME_META in branded:
        branded = branded.replace(_THEME_META, _THEME_META + _SOCIAL_META, 1)
    return branded
