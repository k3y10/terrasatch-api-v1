"""Organization-scoped browser portal renderers."""
# ruff: noqa: E501

from __future__ import annotations

import json
from html import escape

from terrasatch.brand import SATCHY_ASSET_URL


def _attr(value: object) -> str:
    return escape(str(value), quote=True)


def _date_label(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text[:10]


def render_portal_login(
    csrf_token: str,
    *,
    failed: bool,
    notice: str | None = None,
) -> str:
    error = '<div class="alert">Invalid organization user credentials.</div>' if failed else ""
    message = f'<div class="notice">{escape(notice)}</div>' if notice else ""
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>TerraSatch Field Workspace</title>{_styles()}</head><body class="login"><main class="login-card"><a class="brand" href="/"><img src="{escape(SATCHY_ASSET_URL)}" alt=""><span><strong>TERRASATCH</strong><b>FIELD WORKSPACE</b></span></a><h1>Open your TerraSatch workspace</h1><p>Sign in with your TerraSatch account to open the organizations, devices, billing, and field systems connected to you.</p>{message}{error}<form method="post" action="/portal/login"><input type="hidden" name="csrf_token" value="{_attr(csrf_token)}"><label>Email<input type="email" name="email" required autocomplete="username"></label><label>Password<input type="password" name="password" required autocomplete="current-password"></label><button type="submit">Sign in</button></form><div class="account-links"><a href="/portal/forgot-password">Forgot password?</a><a href="/portal/resend-activation">Resend setup email</a></div><small>Your workspace access follows your TerraSatch organization membership.</small></main></body></html>'''


def render_portal_forgot_password(csrf_token: str, *, sent: bool) -> str:
    notice = (
        '<div class="notice">If that account exists, a single-use reset link has been queued.</div>'
        if sent
        else ""
    )
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Reset TerraSatch password</title>{_styles()}</head><body class="login"><main class="login-card"><a class="brand" href="/portal/login"><img src="{escape(SATCHY_ASSET_URL)}" alt=""><span><strong>TERRASATCH</strong><b>ACCOUNT RECOVERY</b></span></a><h1>Reset your password</h1><p>Enter the email used for your TerraSatch account. For privacy, the response is the same whether the address exists or not.</p>{notice}<form method="post" action="/portal/forgot-password"><input type="hidden" name="csrf_token" value="{_attr(csrf_token)}"><label>Email<input type="email" name="email" required autocomplete="email"></label><button type="submit">Send reset link</button></form><small><a href="/portal/login">Back to sign in</a></small></main></body></html>'''


def render_portal_resend_activation(csrf_token: str, *, sent: bool) -> str:
    notice = (
        '<div class="notice">If setup is still pending for that account, a fresh setup email has been queued.</div>'
        if sent
        else ""
    )
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Resend TerraSatch setup</title>{_styles()}</head><body class="login"><main class="login-card"><a class="brand" href="/portal/login"><img src="{escape(SATCHY_ASSET_URL)}" alt=""><span><strong>TERRASATCH</strong><b>ACCOUNT SETUP</b></span></a><h1>Resend your setup email</h1><p>Use this only if checkout completed but your TerraSatch account has not been activated yet.</p>{notice}<form method="post" action="/portal/resend-activation"><input type="hidden" name="csrf_token" value="{_attr(csrf_token)}"><label>Email<input type="email" name="email" required autocomplete="email"></label><button type="submit">Resend setup email</button></form><small><a href="/portal/login">Back to sign in</a></small></main></body></html>'''


def render_portal_reset_password(
    csrf_token: str,
    *,
    error: str | None = None,
) -> str:
    alert = f'<div class="alert">{escape(error)}</div>' if error else ""
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="referrer" content="no-referrer"><title>Create new TerraSatch password</title>{_styles()}</head><body class="login"><main class="login-card"><a class="brand" href="/portal/login"><img src="{escape(SATCHY_ASSET_URL)}" alt=""><span><strong>TERRASATCH</strong><b>ACCOUNT RECOVERY</b></span></a><h1>Create a new password</h1><p>Reset links are single-use and expire shortly. Your password must contain at least 12 characters.</p>{alert}<form method="post" action="/portal/reset-password" id="reset-form"><input type="hidden" name="csrf_token" value="{_attr(csrf_token)}"><input type="hidden" name="token" id="reset-token"><label>New password<input type="password" name="password" minlength="12" required autocomplete="new-password"></label><label>Confirm password<input type="password" name="confirm_password" minlength="12" required autocomplete="new-password"></label><button type="submit">Update password</button></form><small><a href="/portal/login">Back to sign in</a></small></main><script>const token=new URLSearchParams(location.hash.slice(1)).get("token")||"";document.getElementById("reset-token").value=token;history.replaceState({{}},document.title,location.pathname);</script></body></html>'''


def _billing_panel(
    *,
    billing: dict[str, object],
    billing_manage_allowed: bool,
    selected_organization: str,
    csrf_token: str,
) -> str:
    managed = bool(billing.get("managed"))
    if not managed:
        return '''<section class="billing"><div><span>SUBSCRIPTION</span><h2>PILOT / LEGACY ACCESS</h2><p>This organization is not managed by TerraSatch self-service billing. Existing pilot and partner access remains unchanged.</p></div></section>'''

    plan = escape(str(billing.get("plan_code") or "TerraSatch").upper())
    billing_status = escape(str(billing.get("status") or "unknown").upper())
    service_access = escape(str(billing.get("service_access") or "unknown").upper())
    trial_end = _date_label(billing.get("trial_ends_at"))
    period_end = _date_label(billing.get("current_period_end"))
    cancel_at_period_end = bool(billing.get("cancel_at_period_end"))
    date_message = ""
    if trial_end:
        date_message = f"Trial ends {escape(trial_end)}."
    elif period_end:
        date_message = f"Current billing period ends {escape(period_end)}."
    if cancel_at_period_end and period_end:
        date_message = f"Cancellation is scheduled for {escape(period_end)}."

    manage = ""
    if billing_manage_allowed:
        manage = f'''<form method="post" action="/portal/billing"><input type="hidden" name="csrf_token" value="{_attr(csrf_token)}"><input type="hidden" name="organization" value="{_attr(selected_organization)}"><button type="submit" class="billing-action">Manage billing</button></form>'''

    return f'''<section class="billing"><div><span>SUBSCRIPTION</span><h2>{plan} · {billing_status}</h2><p>Service access: <strong>{service_access}</strong>. {date_message}</p></div>{manage}</section>'''


def render_portal(
    *,
    display_name: str,
    email: str,
    role: str,
    access_options: list[tuple[str, str]],
    selected_organization: str,
    selected_name: str,
    sites: list[object],
    devices: list[dict[str, object]],
    summary: dict[str, int],
    billing: dict[str, object],
    billing_manage_allowed: bool,
    edge_troubleshoot_allowed: bool,
    edge_manage_allowed: bool,
    csrf_token: str,
) -> str:
    options = "".join(
        f'<option value="{_attr(org_id)}"{" selected" if org_id == selected_organization else ""}>{escape(name)}</option>'
        for org_id, name in access_options
    )
    rows = []
    for device in devices:
        health = escape(str(device.get("health") or "never"))
        rx = "ON" if device.get("rx_enabled") else "READY" if device.get("rx_supported") else "N/A"
        tx = (
            "ARMED"
            if device.get("tx_enabled")
            else "READY"
            if device.get("tx_supported")
            else "N/A"
        )
        age = device.get("age_seconds")
        age_label = "never" if age is None else f"{age}s" if int(age) < 60 else f"{int(age) // 60}m"
        device_id = str(device.get("id") or "")
        version = str(device.get("agent_version") or "unknown")
        platform = " ".join(
            part for part in (str(device.get("platform") or "").strip(), str(device.get("architecture") or "").strip()) if part
        ) or "unknown platform"
        inspect = (
            f'<a class="inspect-link" href="/portal/edge/{_attr(device_id)}?organization={_attr(selected_organization)}">Inspect</a>'
            if edge_troubleshoot_allowed and device_id
            else '<span class="view-only">View only</span>'
        )
        rows.append(
            f'<tr><td><span class="dot {health}"></span>{health.upper()}<small>{escape(age_label)}</small></td>'
            f"<td><strong>{escape(str(device.get('name') or 'Edge'))}</strong><small>{escape(str(device.get('hostname') or ''))}</small></td>"
            f"<td><strong>{escape(version)}</strong><small>{escape(platform)}</small></td>"
            f"<td><strong>{escape(str(device.get('primary_hardware') or device.get('hardware') or '—'))}</strong><small>{escape(str(device.get('provider') or 'unknown'))}</small></td>"
            f'<td><b class="good">RX {rx}</b></td><td><b class="warn">TX {tx}</b></td><td>{escape(str(device.get("mode") or "IDLE"))}</td><td>{inspect}</td></tr>'
        )
    table = (
        "".join(rows)
        or '<tr><td colspan="8" class="empty">No registered Edge devices for this organization.</td></tr>'
    )
    attention = summary.get("attention", 0)
    billing_html = _billing_panel(
        billing=billing,
        billing_manage_allowed=billing_manage_allowed,
        selected_organization=selected_organization,
        csrf_token=csrf_token,
    )
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(selected_name)} · TerraSatch</title>{_styles()}</head><body><div class="shell"><header><a class="brand" href="/"><img src="{escape(SATCHY_ASSET_URL)}" alt=""><span><strong>TERRASATCH</strong><b>FIELD WORKSPACE</b></span></a><div class="who"><strong>{escape(display_name)}</strong><span>{escape(email)} · {escape(role.upper())}</span></div><form method="post" action="/portal/logout"><input type="hidden" name="csrf_token" value="{_attr(csrf_token)}"><button class="ghost">Sign out</button></form></header><main><section class="headline"><div><h1>{escape(selected_name)}</h1><p>Your connected organization, Edge devices, radio capabilities, billing, and current field status in one place.</p></div><form method="get" action="/portal"><label>Organization<select name="organization" onchange="this.form.submit()">{options}</select></label></form></section><section class="metrics"><div><span>ONLINE</span><b class="good">{summary.get("online", 0)} / {summary.get("total", 0)}</b></div><div><span>SITES</span><b>{summary.get("sites", len(sites))}</b></div><div><span>RX CAPABLE</span><b class="good">{summary.get("rx_capable", 0)}</b></div><div><span>TX CAPABLE</span><b class="warn">{summary.get("tx_capable", 0)}</b></div><div><span>ATTENTION</span><b class="{"warn" if attention else "good"}">{attention}</b></div></section>{billing_html}<section class="panel"><div class="panel-head"><div><span>REGISTERED EDGE FLEET</span><small>{len(sites)} site(s) visible to this membership</small></div><a href="/">Radio console</a></div><div class="table-wrap"><table><thead><tr><th>Health</th><th>Device</th><th>Edge / platform</th><th>Radio hardware</th><th>Receive</th><th>Transmit</th><th>Mode</th><th>Tools</th></tr></thead><tbody>{table}</tbody></table></div></section><section class="policy"><strong>ROLE · {escape(role.upper())}</strong><span>Organization membership controls what this portal can see. {"Edge diagnostics are available to operators and above. " if edge_troubleshoot_allowed else ""}{"Device name, site assignment, and enabled state can be managed by organization admins/owners. " if edge_manage_allowed else ""}Billing changes require organization admin/owner access. Radio transmit capability remains hardware/provider-gated and operator-controlled.</span></section></main></div></body></html>'''


def _pretty_json(value: object) -> str:
    return escape(json.dumps(value or {}, indent=2, sort_keys=True, default=str))


def render_portal_edge_device(
    *,
    display_name: str,
    role: str,
    organization_id: str,
    organization_name: str,
    device: dict[str, object],
    sites: list[object],
    manage_allowed: bool,
    csrf_token: str,
) -> str:
    """Render the organization-scoped Edge troubleshooting surface."""

    health = escape(str(device.get("health") or "never"))
    capabilities = device.get("capabilities") or []
    capability_html = "".join(f"<li><code>{escape(str(item))}</code></li>" for item in capabilities)
    if not capability_html:
        capability_html = "<li class='muted'>No capabilities reported</li>"

    site_options = []
    current_site = str(device.get("site_id") or "")
    for site in sites:
        site_id = str(getattr(site, "id", ""))
        site_name = str(getattr(site, "name", site_id or "Site"))
        selected = " selected" if site_id == current_site else ""
        site_options.append(
            f'<option value="{_attr(site_id)}"{selected}>{escape(site_name)}</option>'
        )

    management = (
        f'''<section class="edge-card edge-manage"><div class="edge-card-head"><span>ADMIN / OWNER</span><h2>Device management</h2></div>
        <form method="post" action="/portal/edge/{_attr(device.get("id") or "")}">
          <input type="hidden" name="csrf_token" value="{_attr(csrf_token)}">
          <input type="hidden" name="organization" value="{_attr(organization_id)}">
          <label>Device name<input name="name" maxlength="255" required value="{_attr(device.get("name") or "Edge")}"></label>
          <label>Assigned site<select name="site_id" required>{''.join(site_options)}</select></label>
          <label>Device state<select name="enabled"><option value="true"{" selected" if device.get("enabled") else ""}>Enabled</option><option value="false"{" selected" if not device.get("enabled") else ""}>Disabled</option></select></label>
          <button type="submit">Save device settings</button>
        </form>
        <p class="muted">This does not enable RF transmit. TX remains provider-, capability-, policy-, and approval-gated.</p></section>'''
        if manage_allowed
        else '''<section class="edge-card"><div class="edge-card-head"><span>MANAGEMENT</span><h2>Operator troubleshooting</h2></div><p class="muted">You can inspect health, hardware, telemetry, capabilities and the effective remote policy. Organization Admin/Owner access is required to rename, move, enable or disable this Edge.</p></section>'''
    )

    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(str(device.get("name") or "Edge"))} · TerraSatch</title>{_styles()}<style>
    .edge-back{{color:var(--orange);text-decoration:none;font:10px var(--mono)}}.edge-title{{display:flex;justify-content:space-between;gap:18px;align-items:flex-end;margin-bottom:16px}}.edge-title h1{{margin:4px 0 0}}.edge-role{{color:var(--muted);font:9px var(--mono)}}.edge-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}}.edge-card{{border:1px solid var(--line);background:rgba(16,21,25,.94);border-radius:10px;padding:16px;min-width:0}}.edge-card-head span{{color:var(--orange);font:8px var(--mono);letter-spacing:.11em}}.edge-card-head h2{{margin:4px 0 12px;font-size:17px}}.edge-kv{{display:grid;grid-template-columns:140px 1fr;gap:7px 14px;margin:0}}.edge-kv dt{{color:var(--muted);font:9px var(--mono)}}.edge-kv dd{{margin:0;overflow-wrap:anywhere}}.edge-state{{display:inline-flex;align-items:center;gap:7px}}.edge-state .dot{{margin:0}}.edge-card pre{{overflow:auto;max-height:320px;background:#080b0d;border:1px solid var(--line);padding:12px;border-radius:7px;font:10px/1.5 var(--mono);white-space:pre-wrap;word-break:break-word}}.edge-card ul{{margin:0;padding-left:18px}}.edge-manage form{{display:grid;grid-template-columns:2fr 1.3fr 1fr auto;gap:10px;align-items:end}}.edge-manage label{{display:grid;gap:5px;color:var(--muted);font:9px var(--mono)}}.edge-manage button{{height:38px;border-color:rgba(244,122,32,.45);background:rgba(244,122,32,.12);color:#ffad59}}.muted{{color:var(--muted)}}.inspect-link{{color:var(--orange);text-decoration:none;font:9px var(--mono)}}.view-only{{color:var(--muted);font:9px var(--mono)}}@media(max-width:900px){{.edge-grid{{grid-template-columns:1fr}}.edge-manage form{{grid-template-columns:1fr}}.edge-title{{align-items:flex-start;flex-direction:column}}}}
    </style></head><body><div class="shell"><header><a class="brand" href="/portal?organization={_attr(organization_id)}"><img src="{escape(SATCHY_ASSET_URL)}" alt=""><span><strong>TERRASATCH</strong><b>EDGE DIAGNOSTICS</b></span></a><div class="who"><strong>{escape(display_name)}</strong><span>{escape(organization_name)} · {escape(role.upper())}</span></div></header><main>
    <a class="edge-back" href="/portal?organization={_attr(organization_id)}">← Back to fleet</a>
    <section class="edge-title"><div><p class="edge-role">{escape(organization_name)} · ROLE {escape(role.upper())}</p><h1>{escape(str(device.get("name") or "Edge"))}</h1><p class="muted">{escape(str(device.get("hostname") or "No hostname reported"))}</p></div><strong class="edge-state"><span class="dot {health}"></span>{health.upper()}</strong></section>
    <div class="edge-grid">
      <section class="edge-card"><div class="edge-card-head"><span>IDENTITY</span><h2>Runtime and assignment</h2></div><dl class="edge-kv">
        <dt>Edge version</dt><dd>{escape(str(device.get("agent_version") or "unknown"))}</dd>
        <dt>Platform</dt><dd>{escape(str(device.get("platform") or "unknown"))} · {escape(str(device.get("architecture") or "unknown"))}</dd>
        <dt>Device ID</dt><dd><code>{escape(str(device.get("id") or ""))}</code></dd>
        <dt>Site ID</dt><dd><code>{escape(current_site)}</code></dd>
        <dt>Enabled</dt><dd>{'YES' if device.get("enabled") else 'NO'}</dd>
        <dt>Last heartbeat</dt><dd>{escape(str(device.get("last_seen_at") or "never"))}</dd>
      </dl></section>
      <section class="edge-card"><div class="edge-card-head"><span>RADIO</span><h2>Capability state</h2></div><dl class="edge-kv">
        <dt>Primary hardware</dt><dd>{escape(str(device.get("primary_hardware") or "No radio hardware reported"))}</dd>
        <dt>Provider</dt><dd>{escape(str(device.get("provider") or "none"))}</dd>
        <dt>Mode</dt><dd>{escape(str(device.get("mode") or "IDLE"))}</dd>
        <dt>Receive</dt><dd>{'ENABLED' if device.get("rx_enabled") else 'READY' if device.get("rx_supported") else 'N/A'}</dd>
        <dt>Transmit</dt><dd>{'ARMED' if device.get("tx_enabled") else 'READY' if device.get("tx_supported") else 'N/A'}</dd>
      </dl><h3>Reported capabilities</h3><ul>{capability_html}</ul></section>
      <section class="edge-card"><div class="edge-card-head"><span>HARDWARE</span><h2>Full reported inventory</h2></div><pre>{_pretty_json(device.get("hardware_inventory"))}</pre></section>
      <section class="edge-card"><div class="edge-card-head"><span>TELEMETRY</span><h2>Latest heartbeat telemetry</h2></div><pre>{_pretty_json(device.get("telemetry"))}</pre></section>
      <section class="edge-card"><div class="edge-card-head"><span>REMOTE POLICY</span><h2>Effective Edge configuration</h2></div><pre>{_pretty_json(device.get("remote_config"))}</pre></section>
      <section class="edge-card"><div class="edge-card-head"><span>SATCHY</span><h2>AI channel binding</h2></div><pre>{_pretty_json(device.get("ai_channel"))}</pre></section>
    </div>{management}
    </main></div></body></html>'''




def _styles() -> str:
    return """<style>:root{color-scheme:dark;--bg:#080b0d;--panel:#101519;--line:rgba(255,255,255,.1);--text:#edf1f0;--muted:#8f989e;--orange:#f47a20;--green:#6ee7a0;--yellow:#f6c65b;--red:#ff6b6b;--mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 70% -20%,rgba(244,122,32,.1),transparent 35%),var(--bg);color:var(--text);font:13px/1.45 Inter,system-ui,sans-serif}.shell{min-height:100vh}header{height:68px;padding:0 28px;border-bottom:1px solid var(--line);display:flex;align-items:center;gap:22px}.brand{display:flex;align-items:center;gap:10px;color:inherit;text-decoration:none;margin-right:auto}.brand img{width:42px;height:42px;object-fit:contain}.brand strong,.brand b{display:block}.brand b{color:var(--orange);font:10px var(--mono);letter-spacing:.11em}.who{text-align:right}.who strong,.who span{display:block}.who span{color:var(--muted);font:9px var(--mono)}button,.ghost{border:1px solid var(--line);background:#11171a;color:var(--text);padding:8px 11px;border-radius:6px;cursor:pointer}main{max-width:1500px;margin:auto;padding:24px 28px}.headline{display:flex;justify-content:space-between;align-items:end;gap:20px;margin-bottom:16px}.headline h1{margin:0;font-size:30px}.headline p{color:var(--muted);margin:5px 0 0}.headline label{display:grid;gap:5px;color:var(--muted);font:9px var(--mono)}select,input{background:#0b1013;border:1px solid var(--line);color:var(--text);padding:9px;border-radius:6px}.metrics{display:grid;grid-template-columns:repeat(5,1fr);border:1px solid var(--line);border-radius:10px;overflow:hidden;margin-bottom:16px}.metrics>div{padding:13px 15px;background:rgba(16,21,25,.92);border-right:1px solid var(--line)}.metrics>div:last-child{border-right:0}.metrics span{display:block;color:var(--muted);font:8px var(--mono);letter-spacing:.1em}.metrics b{display:block;margin-top:4px;font-size:16px}.good{color:var(--green)}.warn{color:var(--yellow)}.billing{display:flex;align-items:center;justify-content:space-between;gap:20px;border:1px solid rgba(244,122,32,.3);background:rgba(244,122,32,.055);padding:15px 17px;border-radius:10px;margin-bottom:16px}.billing span{display:block;color:var(--orange);font:8px var(--mono);letter-spacing:.11em}.billing h2{margin:4px 0 2px;font-size:17px}.billing p{margin:0;color:var(--muted);font-size:10px}.billing-action{border-color:rgba(244,122,32,.45);background:rgba(244,122,32,.12);color:#ffad59;white-space:nowrap}.panel{border:1px solid var(--line);background:rgba(16,21,25,.94);border-radius:10px;overflow:hidden}.panel-head{display:flex;justify-content:space-between;align-items:center;padding:14px 16px;border-bottom:1px solid var(--line)}.panel-head span{display:block;font-weight:800}.panel-head small{color:var(--muted)}.panel-head a{color:var(--orange);text-decoration:none;font:9px var(--mono)}.table-wrap{overflow:auto}table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:12px 14px;border-bottom:1px solid var(--line);vertical-align:top}th{color:var(--muted);font:8px var(--mono);letter-spacing:.08em}td small{display:block;color:var(--muted);margin-top:3px;font-size:9px}.dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:#667078;margin-right:7px}.dot.online{background:var(--green);box-shadow:0 0 8px rgba(110,231,160,.45)}.dot.stale{background:var(--yellow)}.dot.offline{background:var(--red)}.empty{color:var(--muted);text-align:center}.policy{margin-top:13px;border:1px solid var(--line);padding:12px 14px;border-radius:8px;display:flex;gap:18px}.policy strong{color:var(--orange);font:9px var(--mono);white-space:nowrap}.policy span{color:var(--muted);font-size:10px}.login{min-height:100vh;display:grid;place-items:center}.login-card{width:min(430px,calc(100vw - 30px));border:1px solid var(--line);border-radius:12px;background:var(--panel);padding:24px}.login-card .brand{margin-bottom:24px}.login-card h1{margin:0;font-size:24px}.login-card p,.login-card small{color:var(--muted)}.login-card form{display:grid;gap:12px;margin:18px 0}.login-card label{display:grid;gap:5px;color:var(--muted);font-size:10px}.login-card button{background:rgba(244,122,32,.12);border-color:rgba(244,122,32,.4);color:#ffad59}.login-card a{color:#ffad59}.alert{border:1px solid rgba(255,107,107,.35);background:rgba(255,107,107,.08);color:#ff9292;padding:9px;border-radius:6px;margin-top:14px}.notice{border:1px solid rgba(110,231,160,.3);background:rgba(110,231,160,.07);color:#9ff0bb;padding:9px;border-radius:6px;margin-top:14px}.account-links{display:flex;justify-content:space-between;gap:12px;margin:-2px 0 18px;font-size:11px}@media(max-width:850px){header{padding:0 14px}.who{display:none}main{padding:16px 14px}.headline{align-items:stretch;flex-direction:column}.metrics{grid-template-columns:repeat(2,1fr)}.metrics>div{border-bottom:1px solid var(--line)}.billing{align-items:flex-start;flex-direction:column}.policy{flex-direction:column}.panel-head{align-items:flex-start}.table-wrap{font-size:11px}}</style>"""
