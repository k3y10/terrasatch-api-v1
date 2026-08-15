from terrasatch.brand import SASQUATCH_ASSET_PUBLIC_URL, SASQUATCH_ASSET_URL


def test_public_brand_uses_local_sasquatch_asset() -> None:
    assert SASQUATCH_ASSET_URL == "/assets/terralisten-sasquatch.webp"
    assert SASQUATCH_ASSET_PUBLIC_URL == (
        "https://api.terrasatch.com/assets/terralisten-sasquatch.webp"
    )
