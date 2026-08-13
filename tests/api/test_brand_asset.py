from terrasatch.landing import _BRAND_LOGO_URL


def test_landing_uses_current_terrasatch_brand_asset() -> None:
    assert _BRAND_LOGO_URL.startswith("https://www.terrasatch.com/assets/terrasatch-logo-")
    assert _BRAND_LOGO_URL.endswith(".png")
