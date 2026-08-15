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
_SOCIAL_META = f'''  <link rel="icon" type="image/webp" href="{SASQUATCH_ASSET_URL}">\n  <link rel="apple-touch-icon" href="{SASQUATCH_ASSET_URL}">\n  <meta property="og:type" content="website">\n  <meta property="og:site_name" content="TerraSatch">\n  <meta property="og:title" content="TerraSatch · TerraListen Radio Console">\n  <meta property="og:description" content="Receive-only radio intelligence for field operations.">\n  <meta property="og:url" content="https://api.terrasatch.com/">\n  <meta property="og:image" content="{SASQUATCH_ASSET_PUBLIC_URL}">\n  <meta property="og:image:type" content="image/webp">\n  <meta property="og:image:width" content="256">\n  <meta property="og:image:height" content="256">\n  <meta property="og:image:alt" content="Sassy, the TerraSatch Sasquatch holding a field radio">\n  <meta name="twitter:card" content="summary">\n  <meta name="twitter:title" content="TerraSatch · TerraListen Radio Console">\n  <meta name="twitter:description" content="Receive-only radio intelligence for field operations.">\n  <meta name="twitter:image" content="{SASQUATCH_ASSET_PUBLIC_URL}">\n'''


def apply_public_branding(html: str) -> str:
    """Replace the remote logo dependency and add explicit link-preview metadata."""

    branded = html.replace(_REMOTE_SASQUATCH_URL, SASQUATCH_ASSET_URL)
    if _SOCIAL_META not in branded and _THEME_META in branded:
        branded = branded.replace(_THEME_META, _THEME_META + _SOCIAL_META, 1)
    return branded
