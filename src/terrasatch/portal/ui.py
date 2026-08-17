"""Organization-scoped browser portal renderers."""

from __future__ import annotations

from html import escape

from terrasatch.brand import SASQUATCH_ASSET_URL


def _attr(value: object) -> str:
    return escape(str(value), quote=True)


def render_portal_login(csrf_token: str, *, failed: bool) -> str:
    error = '<div class="alert">Invalid organization user credentials.</div>' if failed else ""
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>TerraSatch Organization Portal</title>{_styles()}</head><body class="login"><main class="login-card"><a class="brand" href="/"><img src="{escape(SASQUATCH_ASSET_URL)}" alt=""><span><strong>TERRASATCH</strong><b>ORGANIZATION PORTAL</b></span></a><h1>Field organization sign in</h1><p>Use your individual TerraSatch account. Access is limited to organizations assigned to your membership.</p>{error}<form method="post" action="/portal/login"><input type="hidden" name="csrf_token" value="{_attr(csrf_token)}"><label>Email<input type="email" name="email" required autocomplete="username"></label><label>Password<input type="password" name="password" required autocomplete="current-password"></label><button type="submit">Sign in</button></form><small>TerraSatch superadministrators continue to use <a href="/admin">Admin</a>.</small></main></body></html>'''


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
        tx = "ARMED" if device.get("tx_enabled") else "READY" if device.get("tx_supported") else "N/A"
        age = device.get("age_seconds")
        age_label = "never" if age is None else f"{age}s" if int(age) < 60 else f"{int(age) // 60}m"
        rows.append(
            f'<tr><td><span class="dot {health}"></span>{health.upper()}<small>{escape(age_label)}</small></td>'
            f'<td><strong>{escape(str(device.get("name") or "Edge"))}</strong><small>{escape(str(device.get("hostname") or ""))}</small></td>'
            f'<td><strong>{escape(str(device.get("primary_hardware") or device.get("hardware") or "—"))}</strong><small>{escape(str(device.get("provider") or "unknown"))}</small></td>'
            f'<td><b class="good">RX {rx}</b></td><td><b class="warn">TX {tx}</b></td><td>{escape(str(device.get("mode") or "IDLE"))}</td></tr>'
        )
    table = "".join(rows) or '<tr><td colspan="6" class="empty">No registered Edge devices for this organization.</td></tr>'
    attention = summary.get("attention", 0)
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(selected_name)} · TerraSatch</title>{_styles()}</head><body><div class="shell"><header><a class="brand" href="/"><img src="{escape(SASQUATCH_ASSET_URL)}" alt=""><span><strong>TERRASATCH</strong><b>ORGANIZATION PORTAL</b></span></a><div class="who"><strong>{escape(display_name)}</strong><span>{escape(email)} · {escape(role.upper())}</span></div><form method="post" action="/portal/logout"><input type="hidden" name="csrf_token" value="{_attr(csrf_token)}"><button class="ghost">Sign out</button></form></header><main><section class="headline"><div><h1>{escape(selected_name)}</h1><p>Tenant-scoped Edge health, radio capabilities and current listening state.</p></div><form method="get" action="/portal"><label>Organization<select name="organization" onchange="this.form.submit()">{options}</select></label></form></section><section class="metrics"><div><span>ONLINE</span><b class="good">{summary.get("online", 0)} / {summary.get("total", 0)}</b></div><div><span>SITES</span><b>{summary.get("sites", len(sites))}</b></div><div><span>RX CAPABLE</span><b class="good">{summary.get("rx_capable", 0)}</b></div><div><span>TX CAPABLE</span><b class="warn">{summary.get("tx_capable", 0)}</b></div><div><span>ATTENTION</span><b class="{'warn' if attention else 'good'}">{attention}</b></div></section><section class="panel"><div class="panel-head"><div><span>REGISTERED EDGE FLEET</span><small>{len(sites)} site(s) visible to this membership</small></div><a href="/">Radio console</a></div><div class="table-wrap"><table><thead><tr><th>Health</th><th>Device</th><th>Radio hardware</th><th>Receive</th><th>Transmit</th><th>Mode</th></tr></thead><tbody>{table}</tbody></table></div></section><section class="policy"><strong>ROLE · {escape(role.upper())}</strong><span>Organization membership controls what this portal can see. Radio transmit capability remains hardware/provider-gated and operator-controlled.</span></section></main></div></body></html>'''


def _styles() -> str:
    return '''<style>:root{color-scheme:dark;--bg:#080b0d;--panel:#101519;--line:rgba(255,255,255,.1);--text:#edf1f0;--muted:#8f989e;--orange:#f47a20;--green:#6ee7a0;--yellow:#f6c65b;--red:#ff6b6b;--mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 70% -20%,rgba(244,122,32,.1),transparent 35%),var(--bg);color:var(--text);font:13px/1.45 Inter,system-ui,sans-serif}.shell{min-height:100vh}header{height:68px;padding:0 28px;border-bottom:1px solid var(--line);display:flex;align-items:center;gap:22px}.brand{display:flex;align-items:center;gap:10px;color:inherit;text-decoration:none;margin-right:auto}.brand img{width:42px;height:42px;object-fit:contain}.brand strong,.brand b{display:block}.brand b{color:var(--orange);font:10px var(--mono);letter-spacing:.11em}.who{text-align:right}.who strong,.who span{display:block}.who span{color:var(--muted);font:9px var(--mono)}button,.ghost{border:1px solid var(--line);background:#11171a;color:var(--text);padding:8px 11px;border-radius:6px;cursor:pointer}main{max-width:1500px;margin:auto;padding:24px 28px}.headline{display:flex;justify-content:space-between;align-items:end;gap:20px;margin-bottom:16px}.headline h1{margin:0;font-size:30px}.headline p{color:var(--muted);margin:5px 0 0}.headline label{display:grid;gap:5px;color:var(--muted);font:9px var(--mono)}select,input{background:#0b1013;border:1px solid var(--line);color:var(--text);padding:9px;border-radius:6px}.metrics{display:grid;grid-template-columns:repeat(5,1fr);border:1px solid var(--line);border-radius:10px;overflow:hidden;margin-bottom:16px}.metrics>div{padding:13px 15px;background:rgba(16,21,25,.92);border-right:1px solid var(--line)}.metrics>div:last-child{border-right:0}.metrics span{display:block;color:var(--muted);font:8px var(--mono);letter-spacing:.1em}.metrics b{display:block;margin-top:4px;font-size:16px}.good{color:var(--green)}.warn{color:var(--yellow)}.panel{border:1px solid var(--line);background:rgba(16,21,25,.94);border-radius:10px;overflow:hidden}.panel-head{display:flex;justify-content:space-between;align-items:center;padding:14px 16px;border-bottom:1px solid var(--line)}.panel-head span{display:block;font-weight:800}.panel-head small{color:var(--muted)}.panel-head a{color:var(--orange);text-decoration:none;font:9px var(--mono)}.table-wrap{overflow:auto}table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:12px 14px;border-bottom:1px solid var(--line);vertical-align:top}th{color:var(--muted);font:8px var(--mono);letter-spacing:.08em}td small{display:block;color:var(--muted);margin-top:3px;font-size:9px}.dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:#667078;margin-right:7px}.dot.online{background:var(--green);box-shadow:0 0 8px rgba(110,231,160,.45)}.dot.stale{background:var(--yellow)}.dot.offline{background:var(--red)}.empty{color:var(--muted);text-align:center}.policy{margin-top:13px;border:1px solid var(--line);padding:12px 14px;border-radius:8px;display:flex;gap:18px}.policy strong{color:var(--orange);font:9px var(--mono);white-space:nowrap}.policy span{color:var(--muted);font-size:10px}.login{min-height:100vh;display:grid;place-items:center}.login-card{width:min(430px,calc(100vw - 30px));border:1px solid var(--line);border-radius:12px;background:var(--panel);padding:24px}.login-card .brand{margin-bottom:24px}.login-card h1{margin:0;font-size:24px}.login-card p,.login-card small{color:var(--muted)}.login-card form{display:grid;gap:12px;margin:18px 0}.login-card label{display:grid;gap:5px;color:var(--muted);font-size:10px}.login-card button{background:rgba(244,122,32,.12);border-color:rgba(244,122,32,.4);color:#ffad59}.login-card a{color:#ffad59}.alert{border:1px solid rgba(255,107,107,.35);background:rgba(255,107,107,.08);color:#ff9292;padding:9px;border-radius:6px;margin-top:14px}@media(max-width:850px){header{padding:0 14px}.who{display:none}main{padding:16px 14px}.headline{align-items:stretch;flex-direction:column}.metrics{grid-template-columns:repeat(2,1fr)}.metrics>div{border-bottom:1px solid var(--line)}.policy{flex-direction:column}.panel-head{align-items:flex-start}.table-wrap{font-size:11px}}</style>'''
