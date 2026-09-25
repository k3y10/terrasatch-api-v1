"""Display server-provided access without inventing feature entitlements."""

from html import escape


def render_workspace_access(
    billing: dict[str, object],
    *,
    device_count: int,
    site_count: int,
    online_count: int,
    can_manage: bool,
) -> str:
    managed = bool(billing.get("managed"))
    raw = billing.get("entitlements")
    limits = raw if isinstance(raw, dict) else {}
    access = billing.get("service_access")
    restricted = managed and access not in {"full", "grace"}

    def allowance(key: str) -> str:
        value = limits.get(key)
        return escape(str(value)) if value is not None else "Contact your administrator"

    def card(title: str, state: str, detail: str) -> str:
        return (
            '<article class="access-card"><span class="access-state">'
            f"{escape(state)}</span><h3>{escape(title)}</h3><p>{detail}</p></article>"
        )

    if restricted:
        api_state = "Restricted by billing"
    elif not managed or not limits:
        api_state = "Confirm organization access"
    elif limits.get("api_access") is True:
        api_state = "Included in your plan"
    else:
        api_state = "Not included in your plan"

    edge_state = (
        "Restricted by billing" if restricted else
        "Reporting" if online_count else "Setup needed" if not device_count else "Check connection"
    )
    cards = card(
        "Connected Edge", edge_state,
        f"{online_count} of {device_count} devices reporting. "
        "Pair a device with this organization to send field data. "
        "A reporting device may still have individual capabilities disabled.",
    )
    cards += card(
        "API access", api_state,
        "API requests use this organization's permissions and plan. "
        "An included plan still requires an authorized API key.",
    )
    cards += card(
        "Organization settings", "Admin access" if can_manage else "Administrator required",
        "Owners and admins manage billing and device settings. "
        "Your membership controls which actions you can use.",
    )
    cards += card(
        "More workspace tools", "In development",
        "Additional beta tools will appear as they become available. "
        "Availability and timing are not guaranteed.",
    )
    usage = ""
    if managed and limits:
        entries = [
            ("Sites", f"{site_count} registered · limit {allowance('max_sites')}"),
            ("Edge devices", f"{device_count} registered · limit {allowance('max_edge_devices')}"),
            ("Members", f"Plan limit {allowance('max_members')}"),
            ("Channels", f"Plan limit {allowance('max_channels')}"),
            ("Processing hours", f"Included allowance: {allowance('included_processing_hours')}"),
            ("Retention", f"Days: {allowance('retention_days')}"),
        ]
        usage = '<dl class="plan-limits">' + "".join(
            f"<div><dt>{title}</dt><dd>{detail}</dd></div>" for title, detail in entries
        ) + "</dl><p class='access-note'>Allowances are plan limits, not remaining usage.</p>"
    notice = (
        "Billing needs attention. Ask an organization owner or admin to review access."
        if restricted else
        "Payment needs attention. Temporary grace access may end; review billing now."
        if access == "grace" else
        "This workspace is in beta. Test your workflow and share feedback "
        "before relying on it in the field."
    )
    return (
        '<section class="workspace-access" aria-labelledby="workspace-access-title">'
        f'<div class="beta-notice"><strong>BETA WORKSPACE</strong><p>{notice}</p></div>'
        '<h2 id="workspace-access-title">Your tools and access</h2>'
        '<p class="access-note">Access shown for the selected organization. '
        'Refresh this page after changing billing or connecting a device.</p>'
        f'<div class="access-grid">{cards}</div>{usage}</section>'
    )


ACCESS_STYLES = """<style>
.workspace-access{margin:22px 0 28px}.workspace-access h2{font-size:22px;margin:22px 0 6px}
.beta-notice{border-left:3px solid var(--orange);padding:12px 18px;background:var(--panel)}
.beta-notice strong,.access-state{color:var(--orange);font:11px var(--mono)}
.beta-notice p{margin:6px 0;color:var(--muted)}
.access-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:18px 0}
.access-card{border:1px solid var(--line);background:var(--panel);padding:20px;border-radius:10px}
.access-card h3{font-size:18px;margin:12px 0 8px}
.access-card p{margin:0;color:var(--muted);line-height:1.7}
.access-note{color:var(--muted);font-size:12px}
.plan-limits{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));
gap:1px;background:var(--line);border:1px solid var(--line)}
.plan-limits>div{padding:14px;background:var(--bg)}.plan-limits dt{color:var(--muted)}
.plan-limits dd{margin:5px 0 0;overflow-wrap:anywhere}
@media(max-width:1050px){.access-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:550px){.access-grid,.plan-limits{grid-template-columns:1fr}
.headline select{max-width:100%}}
</style>"""
