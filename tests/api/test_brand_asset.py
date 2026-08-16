from terrasatch.brand import (
    SASQUATCH_ASSET_URL,
    SASQUATCH_PREVIEW_PUBLIC_URL,
    SASQUATCH_PREVIEW_URL,
)


def test_public_brand_uses_local_sasquatch_assets() -> None:
    assert SASQUATCH_ASSET_URL == "/assets/terralisten-sasquatch.webp"
    assert SASQUATCH_PREVIEW_URL == "/assets/terralisten-sasquatch.png"
    assert SASQUATCH_PREVIEW_PUBLIC_URL == (
        "https://api.terrasatch.com/assets/terralisten-sasquatch.png"
    )
