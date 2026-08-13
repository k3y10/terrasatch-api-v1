from terrasatch.landing import _BRAND_LOGO_URL


def test_landing_uses_local_terrasatch_brand_asset() -> None:
    assert _BRAND_LOGO_URL == "/assets/terrasatch-logo.svg"
