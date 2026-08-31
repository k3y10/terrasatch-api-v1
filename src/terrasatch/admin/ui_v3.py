"""Admin dashboard extension for organization member management."""
# ruff: noqa: E501

from __future__ import annotations

from terrasatch.admin.ui_v2 import render_dashboard as render_base_dashboard


def render_dashboard(**kwargs: object) -> str:
    html = render_base_dashboard(**kwargs)
    html = html.replace(
        '<span>ACCESS</span><a href="#keys">› API keys</a>',
        '<span>ACCESS</span><a href="/admin/members">› Members & access</a><a href="#keys">› API keys</a>',
        1,
    )
    html = html.replace(
        '<a href="#fleet">› Registered Edge health</a>',
        '<a href="#fleet">› Registered Edge health</a><a href="/admin/satchy">› Satchy control plane</a><a href="/admin/data-sources">› Data sources</a><a href="/admin/data-inspector">› Data inspector</a>',
        1,
    )
    return html
