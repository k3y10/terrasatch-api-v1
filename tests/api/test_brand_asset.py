from terrasatch.brand import (
    SASQUATCH_ASSET_URL,
    SASQUATCH_PREVIEW_PUBLIC_URL,
    SASQUATCH_PREVIEW_URL,
    SATCHY_ASSET_URL,
    SATCHY_PUBLIC_URL,
    TERRASATCH_LOGO_ASSET_URL,
)


def test_public_brand_uses_current_local_assets() -> None:
    assert TERRASATCH_LOGO_ASSET_URL == "/assets/terrasatch.png"
    assert SATCHY_ASSET_URL == "/assets/satchy.png"
    assert SATCHY_PUBLIC_URL == "https://api.terrasatch.com/assets/satchy.png"


def test_original_sasquatch_constants_remain_compatible_aliases() -> None:
    assert SASQUATCH_ASSET_URL == SATCHY_ASSET_URL
    assert SASQUATCH_PREVIEW_URL == SATCHY_ASSET_URL
    assert SASQUATCH_PREVIEW_PUBLIC_URL == SATCHY_PUBLIC_URL
