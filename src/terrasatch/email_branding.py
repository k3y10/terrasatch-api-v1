"""Shared TerraSatch email identity and lightweight signature rendering."""

from __future__ import annotations

from html import escape

TERRASATCH_SITE = "https://terrasatch.com"
TERRASATCH_TAGLINE = "LISTEN. WATCH. LEARN. ADAPT."

_SHARED_IDENTITIES = {
    "ops@terrasatch.com": "TerraSatch Operations",
    "support@terrasatch.com": "TerraSatch Support",
    "legal@terrasatch.com": "TerraSatch Legal",
    "billing@terrasatch.com": "TerraSatch Billing",
}


def sender_display_name(sender: str, *, user_display_name: str | None = None) -> str:
    normalized = sender.strip().casefold()
    shared = _SHARED_IDENTITIES.get(normalized)
    if shared:
        return shared
    name = (user_display_name or "").strip()
    return f"{name} | TerraSatch" if name else "TerraSatch"


def formatted_sender(sender: str, *, user_display_name: str | None = None) -> str:
    return f"{sender_display_name(sender, user_display_name=user_display_name)} <{sender.strip()}>"


def text_signature(sender: str, *, user_display_name: str | None = None) -> str:
    label = sender_display_name(sender, user_display_name=user_display_name)
    return (
        f"—\n{label}\n"
        f"{TERRASATCH_TAGLINE}\n"
        f"{TERRASATCH_SITE}"
    )


def html_signature(sender: str, *, user_display_name: str | None = None) -> str:
    label = escape(sender_display_name(sender, user_display_name=user_display_name))
    return (
        '<div style="margin-top:28px;padding-top:16px;border-top:1px solid #d9dde0;'
        'font-family:Arial,sans-serif;color:#596168;font-size:12px;line-height:1.5">'
        f'<strong style="color:#171a1d">{label}</strong><br>'
        f'<span>{escape(TERRASATCH_TAGLINE)}</span><br>'
        f'<a href="{TERRASATCH_SITE}" style="color:#d97706;text-decoration:none">'
        'terrasatch.com</a></div>'
    )


def render_human_email(
    text: str,
    *,
    sender: str,
    user_display_name: str | None = None,
) -> tuple[str, str]:
    body = text.strip()
    signed_text = f"{body}\n\n{text_signature(sender, user_display_name=user_display_name)}"
    safe_body = escape(body).replace("\n", "<br>")
    html = (
        '<!doctype html><html><body style="margin:0;background:#ffffff;color:#171a1d;'
        'font-family:Arial,sans-serif">'
        '<div style="max-width:640px;margin:0 auto;padding:32px 24px;'
        'font-size:15px;line-height:1.65">'
        f'<div>{safe_body}</div>'
        f'{html_signature(sender, user_display_name=user_display_name)}'
        '</div></body></html>'
    )
    return signed_text, html
