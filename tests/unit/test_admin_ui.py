from terrasatch.admin.ui import _styles, render_login


def test_admin_ui_uses_orange_terminal_theme() -> None:
    styles = _styles()
    html = render_login("csrf-token", failed=False)

    assert "--accent:#ff8a00" in styles
    assert "#166534" not in styles
    assert "ts-admin@terrasatch" in html
    assert "establish session" in html
    assert "/assets/terralisten-sasquatch.webp" in html
