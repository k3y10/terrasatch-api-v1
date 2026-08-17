"""Terminal-inspired HTML renderers for the TerraSatch admin browser surfaces."""
# ruff: noqa: E501

from __future__ import annotations

from html import escape

from terrasatch.admin.commands import (
    device_supports_receive,
    device_supports_transmit,
    radio_config,
    radio_mode,
)
from terrasatch.brand import SASQUATCH_ASSET_URL


def _attr(value: object) -> str:
    return escape(str(value), quote=True)


def render_login(csrf_token: str, *, failed: bool) -> str:
    error = (
        '<div class="terminal-alert error"><span>auth:</span> invalid credentials</div>'
        if failed
        else ""
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#08090b"><title>TerraSatch Admin Console</title>{_styles()}</head>
<body class="login-shell"><main class="login-terminal" aria-labelledby="login-title">
<div class="terminal-chrome"><span></span><span></span><span></span><b>api.terrasatch.com / secure admin</b></div>
<section class="login-content"><div class="login-brand"><img src="{escape(SASQUATCH_ASSET_URL)}" alt="TerraSatch Sasquatch"><div><strong>TERRASATCH</strong><small>ADMIN CONSOLE</small></div></div>
<div class="boot-lines"><p><span class="prompt">ts-admin@terrasatch:~$</span> init secure-session</p><p><span class="dim">[ok]</span> TLS endpoint verified</p><p><span class="dim">[ok]</span> session protection armed</p></div>
<h1 id="login-title">Authenticate operator</h1><p class="subtle">Private control-plane access. Session authentication and CSRF protection remain enforced.</p>{error}
<form method="post" action="/admin/login" class="terminal-form"><input type="hidden" name="csrf_token" value="{_attr(csrf_token)}"><label><span>operator@email</span><input required type="email" name="email" autocomplete="username" placeholder="operator@terrasatch.com"></label><label><span>password</span><input required type="password" name="password" autocomplete="current-password" placeholder="••••••••••••"></label><button type="submit"><span>→</span> establish session</button></form><p class="login-foot">LISTEN. WATCH. LEARN. ADAPT.</p>
</section></main></body></html>"""


def render_dashboard(
    *,
    report_status: str,
    components: list[object],
    endpoints: list[object],
    errors: list[object],
    organizations: list[object],
    selected_organization: str,
    selected_name: str,
    selected_slug: str,
    selected_enabled: bool,
    sites: list[object],
    edge_devices: list[object],
    api_keys: list[object],
    csrf_token: str,
    error_message: str | None,
) -> str:
    component_rows = "".join(
        f"<tr><td><span class='status-dot {escape(component.status)}'></span>{escape(component.name)}</td><td class='status-text {escape(component.status)}'>{escape(component.status)}</td><td>{escape(component.detail or '')}</td></tr>"
        for component in components
    )
    endpoint_rows = "".join(
        f"<tr><td class='method'>{escape(endpoint.method)}</td><td><code>{escape(endpoint.path)}</code></td><td>{escape(endpoint.authorization)}</td><td>{escape(endpoint.summary or '')}</td></tr>"
        for endpoint in endpoints
    )
    error_rows = "".join(
        f"<tr><td>{error.http_status}</td><td><code>{escape(error.code)}</code></td><td>{escape(error.meaning)}</td></tr>"
        for error in errors
    )
    organization_options = "".join(
        f"<option value='{_attr(organization.id)}'{' selected' if str(organization.id) == selected_organization else ''}>{escape(organization.name)}{' [disabled]' if not organization.enabled else ''}</option>"
        for organization in organizations
    )
    org_rows = "".join(
        f"<tr><td><code>{escape(str(org.id))}</code></td><td>{escape(org.name)}</td><td>{escape(org.slug)}</td><td class='status-text'>{'enabled' if org.enabled else 'disabled'}</td><td><button type='button' class='mini' data-command='org select {_attr(org.id)}'>select</button></td></tr>"
        for org in organizations
    ) or "<tr><td colspan='5' class='dim'>No organizations.</td></tr>"

    site_rows = "".join(
        f"<tr><td><code>{escape(str(site.id))}</code></td><td>{escape(site.name)}</td><td>{escape(site.slug)}</td><td class='status-text'>{'enabled' if site.enabled else 'disabled'}</td><td class='actions'><button type='button' class='mini' data-prefill='site rename {_attr(site.id)} &quot;{_attr(site.name)}&quot;'>rename</button><button type='button' class='mini {'danger' if site.enabled else ''}' data-command='site {'disable' if site.enabled else 'enable'} {_attr(site.id)}{' --confirm' if site.enabled else ''}'>{'disable' if site.enabled else 'enable'}</button></td></tr>"
        for site in sites
    ) or "<tr><td colspan='5' class='dim'>Select an organization to load sites.</td></tr>"

    device_rows_parts: list[str] = []
    for device in edge_devices:
        rx_supported = device_supports_receive(device)
        tx_supported = device_supports_transmit(device)
        config = radio_config(device)
        rx_enabled = rx_supported and bool(config.get("receive_enabled", rx_supported))
        tx_enabled = tx_supported and bool(config.get("transmit_enabled", False))
        rx_action = (
            f"<button type='button' class='mini' data-command='edge rx {_attr(device.id)} {'off' if rx_enabled else 'on'}'>RX {'on' if rx_enabled else 'off'}</button>"
            if rx_supported
            else "<span class='cap unavailable'>RX unavailable</span>"
        )
        tx_action = (
            f"<button type='button' class='mini {'tx-on' if tx_enabled else ''}' data-command='edge tx {_attr(device.id)} {'off' if tx_enabled else 'on --confirm'}'>TX {'on' if tx_enabled else 'off'}</button>"
            if tx_supported
            else "<span class='cap unavailable'>TX unavailable</span>"
        )
        device_rows_parts.append(
            f"<tr><td><code>{escape(str(device.id))}</code></td><td>{escape(device.name)}<small class='block'>{escape(device.hostname or '')}</small></td><td><span class='mode'>{escape(radio_mode(device))}</span></td><td><span class='cap {'available' if rx_supported else 'unavailable'}'>RX</span> <span class='cap {'available' if tx_supported else 'unavailable'}'>TX</span><small class='block'>{escape(', '.join(device.capabilities) if device.capabilities else 'no capabilities reported')}</small></td><td class='actions'>{rx_action}{tx_action}<button type='button' class='mini' data-prefill='edge rename {_attr(device.id)} &quot;{_attr(device.name)}&quot;'>rename</button><button type='button' class='mini {'danger' if device.enabled else ''}' data-command='edge {'disable' if device.enabled else 'enable'} {_attr(device.id)}{' --confirm' if device.enabled else ''}'>{'disable' if device.enabled else 'enable'}</button></td></tr>"
        )
    device_rows = "".join(device_rows_parts) or "<tr><td colspan='5' class='dim'>No Edge devices loaded for this organization.</td></tr>"

    key_rows = "".join(
        f"<tr><td><code>{escape(str(key.id))}</code></td><td>{escape(key.name)}</td><td>{escape(key.key_prefix)}</td><td>{escape(', '.join(key.scopes))}</td><td class='status-text'>{'revoked' if key.revoked_at else 'active'}</td><td>{'' if key.revoked_at else f'<button type=\"button\" class=\"mini danger\" data-command=\"key revoke {_attr(key.id)} --confirm\">revoke</button>'}</td></tr>"
        for key in api_keys
    ) or "<tr><td colspan='6' class='dim'>No API keys loaded.</td></tr>"

    error_box = f"<div class='terminal-alert error'><span>error:</span> {escape(error_message)}</div>" if error_message else ""
    status_upper = escape(report_status.upper())
    org_state = "enabled" if selected_enabled else "disabled"
    org_controls = ""
    if selected_organization:
        org_controls = f"""
        <div class="inspector-actions"><button type="button" class="mini" data-prefill="org rename {_attr(selected_organization)} &quot;{_attr(selected_name)}&quot;">rename</button>
        <button type="button" class="mini {'danger' if selected_enabled else ''}" data-command="org {'disable' if selected_enabled else 'enable'} {_attr(selected_organization)}{' --confirm' if selected_enabled else ''}">{'disable' if selected_enabled else 'enable'}</button></div>"""

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#08090b"><title>TerraSatch Admin Console</title>{_styles()}</head><body>
<div class="admin-shell"><aside class="sidebar"><a class="brand" href="/admin"><img src="{escape(SASQUATCH_ASSET_URL)}" alt=""><span><strong>TERRASATCH</strong><small>ADMIN CONSOLE</small></span></a>
<div class="sidebar-status"><span class="status-dot {escape(report_status)}"></span><div><small>SYSTEM STATUS</small><strong>{status_upper}</strong></div></div>
<nav aria-label="Admin console"><span>CONSOLE</span><a href="#terminal">› Terminal</a><span>TENANT</span><a href="#tenant">› Organizations</a><a href="#sites">› Sites</a><span>EDGE</span><a href="#radio">› Radio capability</a><a href="/admin/edge/pair">› Pairings</a><span>ACCESS</span><a href="#keys">› API keys</a><span>SYSTEM</span><a href="#system">› Components</a><a href="#reference">› API reference</a><a href="/docs">› OpenAPI docs</a></nav>
<div class="sidebar-foot"><small>CAPABILITY-GATED RADIO</small><p>RX/TX policy follows reported provider capabilities.</p><form id="logout-form" method="post" action="/admin/logout"><input type="hidden" name="csrf_token" value="{_attr(csrf_token)}"><button class="button-ghost" type="submit">logout</button></form></div></aside>
<main class="workspace"><header class="workspace-header"><div><p class="shell-path">ts-admin@terrasatch:<span>~</span>$</p><h1>Operations Console</h1></div><div class="connection"><span class="status-dot {escape(report_status)}"></span>{status_upper}</div></header>{error_box}

<section class="capability-strip"><div><small>RADIO POLICY</small><strong>PROVIDER-AWARE RX / TX</strong><p>Transmit can only be enabled when the Edge device reports a TX-capable provider/adapter.</p></div><div><small>CONTEXT</small><strong>{escape(selected_name)}</strong><p>{escape(selected_slug or 'select an organization')}</p></div><div><small>SAFETY</small><strong>OPERATOR CONFIRMATION</strong><p>TX enablement is explicit and stored in remote Edge configuration.</p></div></section>

<div class="main-grid"><section id="terminal" class="terminal-window"><div class="terminal-chrome"><span></span><span></span><span></span><b>terrasatch-control-plane — controlled operator session</b></div>
<div class="terminal-body" id="terminal-output" aria-live="polite"><p><span class="prompt">ts-admin@terrasatch:~$</span> help</p><p class="dim">Type help for real administrative commands. This console never exposes arbitrary OS shell execution.</p><p><span class="prompt">ts-admin@terrasatch:~$</span> tenant current</p><p><span class="terminal-key">ORG</span><span>{escape(selected_name)}</span></p><p><span class="terminal-key">STATUS</span><span>{org_state}</span></p><p><span class="terminal-key">SITES</span><span>{len(sites)}</span></p><p><span class="terminal-key">EDGE</span><span>{len(edge_devices)}</span></p></div>
<form id="terminal-form" class="command-line" autocomplete="off"><input type="hidden" id="console-csrf" value="{_attr(csrf_token)}"><input type="hidden" id="console-org" value="{_attr(selected_organization)}"><label for="terminal-command" class="sr-only">Admin console command</label><span class="prompt">ts-admin@terrasatch:~$</span><input id="terminal-command" name="command" spellcheck="false" placeholder="org list, site list, edge list, help"></form>
<div class="terminal-actions"><button type="button" data-command="help">help</button><button type="button" data-command="org list">org list</button><button type="button" data-command="site list">site list</button><button type="button" data-command="edge list">edge list</button><button type="button" data-command="key list">key list</button><button type="button" data-local="clear">clear</button></div></section>

<aside class="inspector"><div class="inspector-head"><small>CONTEXT</small><strong>{escape(selected_name)}</strong></div><dl><dt>ID</dt><dd><code>{escape(selected_organization or '—')}</code></dd><dt>Slug</dt><dd>{escape(selected_slug or '—')}</dd><dt>Status</dt><dd>{org_state}</dd><dt>Sites</dt><dd>{len(sites)}</dd><dt>Edge</dt><dd>{len(edge_devices)}</dd><dt>API keys</dt><dd>{len(api_keys)}</dd></dl>{org_controls}<div class="command-help"><small>EDIT EXAMPLES</small><code>org rename &lt;id&gt; "New Name"</code><code>site rename &lt;uuid&gt; "New Name"</code><code>edge tx &lt;uuid&gt; on --confirm</code></div></aside></div>

<section id="tenant" class="console-section"><div class="section-heading"><div><small>// TENANT</small><h2>Organizations</h2></div><span class="section-index">01</span></div><div class="split-grid"><div class="console-pane"><h3>context</h3><form method="get" action="/admin"><label>Organization<select name="organization" onchange="this.form.submit()"><option value="">Select organization</option>{organization_options}</select></label></form></div><div class="console-pane"><h3>create</h3><form method="post" action="/admin/organizations"><input type="hidden" name="csrf_token" value="{_attr(csrf_token)}"><label>Name<input required name="name" placeholder="Organization name"></label><button type="submit">create organization</button></form></div></div><div class="table-wrap"><table><thead><tr><th>ID</th><th>Name</th><th>Slug</th><th>Status</th><th></th></tr></thead><tbody>{org_rows}</tbody></table></div></section>

<section id="sites" class="console-section"><div class="section-heading"><div><small>// SITES</small><h2>Site management</h2></div><span class="section-index">02</span></div><div class="console-pane"><form method="post" action="/admin/sites"><input type="hidden" name="csrf_token" value="{_attr(csrf_token)}"><input type="hidden" name="organization" value="{_attr(selected_organization)}"><div class="field-grid"><label>New site<input required name="name" placeholder="Site name" {'disabled' if not selected_organization else ''}></label><div class="align-end"><button type="submit" {'disabled' if not selected_organization else ''}>create site</button></div></div></form></div><div class="table-wrap"><table><thead><tr><th>ID</th><th>Name</th><th>Slug</th><th>Status</th><th>Actions</th></tr></thead><tbody>{site_rows}</tbody></table></div></section>

<section id="radio" class="console-section"><div class="section-heading"><div><small>// EDGE RADIO</small><h2>Provider capability & policy</h2></div><span class="section-index">03</span></div><div class="radio-note"><strong>RX/TX is capability-gated.</strong> Nooelec / RTL-SDR is receive-capable only. TX controls appear only when an Edge provider reports a transmit capability. Enabling TX changes remote policy; the provider adapter still owns actual hardware execution.</div><div class="table-wrap"><table><thead><tr><th>Device</th><th>Name</th><th>Mode</th><th>Capabilities</th><th>Controls</th></tr></thead><tbody>{device_rows}</tbody></table></div></section>

<section id="keys" class="console-section"><div class="section-heading"><div><small>// ACCESS</small><h2>API keys</h2></div><span class="section-index">04</span></div><div class="console-pane"><form method="post" action="/admin/api-keys"><input type="hidden" name="csrf_token" value="{_attr(csrf_token)}"><input type="hidden" name="organization" value="{_attr(selected_organization)}"><div class="field-grid"><label>Label<input required name="name" placeholder="edge-node-prod" {'disabled' if not selected_organization else ''}></label><label>Scopes<input name="scope" value="read:events" {'disabled' if not selected_organization else ''}></label></div><button type="submit" {'disabled' if not selected_organization else ''}>issue credential</button></form></div><div class="table-wrap"><table><thead><tr><th>ID</th><th>Name</th><th>Prefix</th><th>Scopes</th><th>Status</th><th></th></tr></thead><tbody>{key_rows}</tbody></table></div></section>

<section id="system" class="console-section"><div class="section-heading"><div><small>// SYSTEM</small><h2>Live components</h2></div><span class="section-index">05</span></div><div class="table-wrap"><table><thead><tr><th>Component</th><th>Status</th><th>Detail</th></tr></thead><tbody>{component_rows}</tbody></table></div></section>
<section id="reference" class="console-section"><div class="section-heading"><div><small>// REFERENCE</small><h2>Implemented API</h2></div><span class="section-index">06</span></div><div class="table-wrap"><table><thead><tr><th>Method</th><th>Path</th><th>Authorization</th><th>Purpose</th></tr></thead><tbody>{endpoint_rows}</tbody></table></div></section>
<section class="console-section"><div class="section-heading"><div><small>// RESPONSES</small><h2>Common responses</h2></div><span class="section-index">07</span></div><div class="table-wrap"><table><thead><tr><th>HTTP</th><th>Code</th><th>Meaning</th></tr></thead><tbody>{error_rows}</tbody></table></div></section>
<footer>TerraSatch Admin Console <span>•</span> LISTEN. WATCH. LEARN. ADAPT.</footer></main></div>{_terminal_script()}</body></html>"""


def render_one_time_key(token: str, organization: str) -> str:
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#08090b"><title>TerraSatch API Key</title>{_styles()}</head><body class="login-shell"><main class="login-terminal key-terminal"><div class="terminal-chrome"><span></span><span></span><span></span><b>credential issuance — one time output</b></div><section class="login-content"><div class="login-brand"><img src="{escape(SASQUATCH_ASSET_URL)}" alt=""><div><strong>TERRASATCH</strong><small>ADMIN CONSOLE</small></div></div><p><span class="prompt">ts-admin@terrasatch:~$</span> api-key issue</p><h1>Credential generated</h1><div class="terminal-alert warning"><span>warning:</span> this token is shown only in this response.</div><div class="token-block"><code id="issued-token">{escape(token)}</code><button type="button" onclick="navigator.clipboard.writeText(document.getElementById('issued-token').textContent)">copy token</button></div><p><a class="text-link" href="/admin?organization={_attr(organization)}">← return to operations console</a></p></section></main></body></html>"""


def render_edge_pair(
    *,
    code: str,
    selected_org: str,
    approved: str | None,
    error: str | None,
    organizations: list[object],
    sites: list[object],
    csrf_token: str,
) -> str:
    org_options = "".join(
        f'<option value="{_attr(org.id)}" {"selected" if str(org.id) == selected_org else ""}>{escape(org.name)}</option>'
        for org in organizations
    )
    site_options = "".join(
        f'<option value="{_attr(site.id)}">{escape(site.name)}</option>' for site in sites
    )
    message = ""
    if approved:
        message = f'<div class="terminal-alert"><span>[approved]</span> device pairing <strong>{escape(approved)}</strong> is ready for credential claim.</div>'
    elif error:
        message = f'<div class="terminal-alert error"><span>[error]</span> {escape(error)}</div>'
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#08090b"><title>TerraSatch Edge Pairing</title>{_styles()}</head><body><div class="admin-shell"><aside class="sidebar"><a class="brand" href="/admin"><img src="{escape(SASQUATCH_ASSET_URL)}" alt=""><span><strong>TERRASATCH</strong><small>ADMIN CONSOLE</small></span></a><nav><span>OPERATIONS</span><a href="/admin">‹ Operations console</a><a href="/admin/edge/pair">› Edge pairing</a></nav><div class="sidebar-foot"><small>CAPABILITY-GATED RADIO</small><p>Pair first; RX/TX policy is configured per reported provider capability.</p></div></aside><main class="workspace"><header class="workspace-header"><div><p class="shell-path">ts-admin@terrasatch:<span>~</span>$ edge pair</p><h1>Approve TerraSatch Edge</h1></div><div class="connection"><span class="status-dot healthy"></span>SECURE SESSION</div></header>{message}<section class="terminal-window"><div class="terminal-chrome"><span></span><span></span><span></span><b>pairing workflow</b></div><div class="terminal-body compact-terminal"><p><span class="prompt">ts-admin@terrasatch:~$</span> pairing verify --code {escape(code or 'ABCD-2345')}</p><p class="subtle">Match the code shown by the field computer, load its organization sites, then approve the device.</p></div></section><section class="console-section"><div class="section-heading"><div><small>// EDGE</small><h2>Pair field node</h2></div><span class="section-index">01</span></div><div class="split-grid"><div class="console-pane"><h3>load destination</h3><form method="get" action="/admin/edge/pair"><label>Pairing code<input name="code" value="{_attr(code)}" placeholder="ABCD-2345" required></label><label>Organization<select name="organization" required><option value="">Select organization</option>{org_options}</select></label><button type="submit">load sites</button></form></div><div class="console-pane"><h3>approve device</h3><form method="post" action="/admin/edge/pair"><input type="hidden" name="csrf_token" value="{_attr(csrf_token)}"><input type="hidden" name="organization" value="{_attr(selected_org)}"><label>Pairing code<input name="code" value="{_attr(code)}" required></label><label>Site<select name="site_id" required><option value="">Select site</option>{site_options}</select></label><button type="submit" {'disabled' if not sites else ''}>approve pairing</button></form></div></div></section><footer>TerraSatch Edge <span>•</span> provider-aware radio control</footer></main></div></body></html>"""


def _terminal_script() -> str:
    return """<script>
(() => {
 const form=document.getElementById('terminal-form'),input=document.getElementById('terminal-command'),output=document.getElementById('terminal-output');
 if(!form||!input||!output)return;
 const csrf=document.getElementById('console-csrf')?.value||'',org=document.getElementById('console-org')?.value||'';
 const history=[];let cursor=0;
 const write=(text,cls='')=>{const p=document.createElement('p');if(cls)p.className=cls;p.textContent=text;output.appendChild(p);output.scrollTop=output.scrollHeight};
 const send=async(raw)=>{const command=raw.trim();if(!command)return;write(`ts-admin@terrasatch:~$ ${command}`,'echo-command');history.push(command);cursor=history.length;
   const lower=command.toLowerCase();if(lower==='clear'||lower==='cls'){output.replaceChildren();return}if(lower==='docs'){window.location.assign('/docs');return}if(lower==='logout'){document.getElementById('logout-form')?.submit();return}
   const body=new URLSearchParams({command,organization:org,csrf_token:csrf});
   try{const response=await fetch('/admin/command',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body});const data=await response.json();(data.lines||[]).forEach(line=>write(line,data.ok?'':'terminal-error-line'));if(data.redirect)setTimeout(()=>window.location.assign(data.redirect),180)}catch(error){write('error: command transport failed','terminal-error-line')}
 };
 form.addEventListener('submit',event=>{event.preventDefault();const value=input.value;input.value='';send(value)});
 document.querySelectorAll('[data-command]').forEach(el=>el.addEventListener('click',()=>send(el.dataset.command||'')));
 document.querySelectorAll('[data-prefill]').forEach(el=>el.addEventListener('click',()=>{input.value=el.dataset.prefill||'';input.focus();input.setSelectionRange(input.value.length,input.value.length)}));
 document.querySelectorAll('[data-local="clear"]').forEach(el=>el.addEventListener('click',()=>output.replaceChildren()));
 input.addEventListener('keydown',event=>{if(event.key==='ArrowUp'){event.preventDefault();cursor=Math.max(0,cursor-1);input.value=history[cursor]||''}else if(event.key==='ArrowDown'){event.preventDefault();cursor=Math.min(history.length,cursor+1);input.value=history[cursor]||''}else if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='l'){event.preventDefault();output.replaceChildren()}});
})();
</script>"""


def _styles() -> str:
    return """<style>
:root{--bg:#08090b;--panel:#0d1013;--panel2:#101419;--line:#292e34;--line2:#3a4149;--text:#e8eaed;--muted:#929aa4;--muted2:#5f6872;--accent:#ff8a00;--accent2:#ffb15c;--accent-soft:rgba(255,138,0,.12);--danger:#ff5d5d;--danger-soft:rgba(255,93,93,.1);--mono:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,"Liberation Mono","Courier New",monospace}*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:radial-gradient(circle at 80% -10%,rgba(255,138,0,.09),transparent 32%),var(--bg);color:var(--text);font:13px/1.5 var(--mono);min-height:100vh}body:before{content:"";position:fixed;inset:0;pointer-events:none;opacity:.16;background-image:linear-gradient(rgba(255,255,255,.018) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.014) 1px,transparent 1px);background-size:24px 24px}a{color:inherit}.admin-shell{display:grid;grid-template-columns:238px minmax(0,1fr);min-height:100vh}.sidebar{position:sticky;top:0;height:100vh;border-right:1px solid var(--line);background:rgba(8,9,11,.97);padding:20px 16px;display:flex;flex-direction:column;z-index:3}.brand{display:flex;align-items:center;gap:11px;text-decoration:none;padding:4px 5px 18px;border-bottom:1px solid var(--line)}.brand img,.login-brand img{width:42px;height:42px;object-fit:contain}.brand strong,.login-brand strong{display:block;font-size:14px;letter-spacing:.08em}.brand small,.login-brand small{display:block;color:var(--accent);font-size:10px;letter-spacing:.12em}.sidebar-status{display:flex;align-items:center;gap:10px;padding:16px 5px;border-bottom:1px solid var(--line)}.sidebar-status small{display:block;color:var(--muted);font-size:9px;letter-spacing:.12em}.sidebar-status strong{display:block;color:var(--accent2);font-size:11px;margin-top:3px}.status-dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--accent);box-shadow:0 0 12px rgba(255,138,0,.5);margin-right:8px}.status-dot.unhealthy,.status-dot.degraded,.status-dot.error{background:var(--danger);box-shadow:0 0 12px rgba(255,93,93,.45)}nav{padding:12px 0;overflow:auto}nav span{display:block;color:var(--muted2);font-size:9px;letter-spacing:.15em;padding:13px 8px 5px}nav a{display:block;text-decoration:none;color:#bac0c7;padding:6px 9px;border-radius:5px;font-size:11px}nav a:hover{background:var(--accent-soft);color:var(--accent2)}.sidebar-foot{margin-top:auto;border-top:1px solid var(--line);padding:14px 5px 2px}.sidebar-foot small{color:var(--accent);font-size:9px;letter-spacing:.12em}.sidebar-foot p{color:var(--muted);font-size:10px}.workspace{min-width:0;padding:24px 30px 34px;max-width:1580px;width:100%;margin:0 auto}.workspace-header{display:flex;justify-content:space-between;align-items:flex-end;padding-bottom:18px;border-bottom:1px solid var(--line);margin-bottom:16px}.shell-path{color:var(--accent);font-size:11px;margin:0 0 3px}.shell-path span{color:var(--accent2)}h1,h2,h3,p{margin-top:0}h1{font-size:22px;margin-bottom:0}h2{font-size:16px;margin-bottom:0}h3{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--accent2)}.connection{border:1px solid rgba(255,138,0,.35);background:var(--accent-soft);color:var(--accent2);padding:7px 10px;border-radius:5px;font-size:10px;letter-spacing:.08em}.capability-strip{display:grid;grid-template-columns:1.4fr 1fr 1.2fr;border:1px solid rgba(255,138,0,.42);background:rgba(255,138,0,.035);border-radius:8px;margin-bottom:16px;overflow:hidden}.capability-strip>div{padding:14px 16px;border-right:1px solid rgba(255,138,0,.18)}.capability-strip>div:last-child{border-right:0}.capability-strip small{display:block;color:var(--accent);font-size:9px;letter-spacing:.12em}.capability-strip strong{display:block;color:var(--accent2);font-size:12px;margin-top:3px}.capability-strip p{color:var(--muted);font-size:10px;margin:4px 0 0}.main-grid{display:grid;grid-template-columns:minmax(0,1fr) 330px;gap:14px;align-items:start}.terminal-window,.console-section,.inspector{border:1px solid var(--line);background:rgba(11,13,16,.94);border-radius:8px;overflow:hidden}.terminal-chrome{height:35px;display:flex;align-items:center;gap:6px;padding:0 12px;border-bottom:1px solid var(--line);background:#0a0c0f}.terminal-chrome>span{width:8px;height:8px;border-radius:50%;background:#5f300d}.terminal-chrome>span:nth-child(2){background:#784614}.terminal-chrome>span:nth-child(3){background:#9a611b}.terminal-chrome b{font-weight:500;color:var(--muted);font-size:10px;margin-left:6px}.terminal-body{padding:18px 18px 10px;min-height:300px;max-height:480px;overflow:auto;font-size:11px}.terminal-body p{margin:0 0 5px;white-space:pre-wrap}.prompt{color:var(--accent);font-weight:700}.terminal-key{display:inline-block;width:82px;color:#c7ccd2}.command-line{display:flex;align-items:center;gap:9px;border-top:1px solid var(--line);padding:11px 18px;background:#090b0d}.command-line input{flex:1;border:0;outline:0;background:transparent;color:var(--text);padding:4px}.terminal-actions{display:flex;flex-wrap:wrap;gap:6px;padding:9px 18px 11px;border-top:1px solid #171b1f}.terminal-actions button,.mini{margin:0;padding:5px 8px;border:1px solid var(--line2);background:#0d1013;color:var(--muted);border-radius:4px;font:10px var(--mono);cursor:pointer}.terminal-actions button:hover,.mini:hover{border-color:rgba(255,138,0,.5);color:var(--accent2)}.mini.danger{color:#ff9292}.mini.tx-on{background:var(--accent-soft);color:var(--accent2);border-color:rgba(255,138,0,.5)}.echo-command{color:#d5d8dc}.terminal-error-line{color:var(--danger)}.inspector{position:sticky;top:18px}.inspector-head{padding:15px 16px;border-bottom:1px solid var(--line)}.inspector-head small{display:block;color:var(--accent);font-size:9px}.inspector-head strong{display:block;margin-top:3px}.inspector dl{display:grid;grid-template-columns:75px 1fr;gap:8px 10px;padding:14px 16px;margin:0;font-size:10px}.inspector dt{color:var(--muted2)}.inspector dd{margin:0;min-width:0;overflow-wrap:anywhere}.inspector-actions{display:flex;gap:7px;padding:0 16px 14px}.command-help{border-top:1px solid var(--line);padding:13px 16px}.command-help small{display:block;color:var(--accent);font-size:9px;margin-bottom:6px}.command-help code{display:block;color:var(--muted);font-size:9px;padding:3px 0;overflow-wrap:anywhere}.console-section{margin:16px 0}.section-heading{display:flex;justify-content:space-between;align-items:flex-start;padding:15px 18px;border-bottom:1px solid var(--line)}.section-heading small{display:block;color:var(--accent);font-size:9px;letter-spacing:.14em}.section-index{color:#353c44;font-size:20px;font-weight:700}.split-grid{display:grid;grid-template-columns:1fr 1fr}.console-pane{padding:17px 18px;border-right:1px solid var(--line)}.split-grid>.console-pane:last-child{border-right:0}.table-wrap{overflow:auto}table{border-collapse:collapse;width:100%;min-width:760px;font-size:10px}th,td{text-align:left;padding:9px 13px;border-top:1px solid #1b1f24;vertical-align:top}thead th{border-top:0;background:#0a0d10;color:var(--muted2);font-size:8px;letter-spacing:.11em;text-transform:uppercase}tbody tr:hover{background:rgba(255,138,0,.025)}td code{color:#bec4ca}.method,.status-text{color:var(--accent2)}.actions{display:flex;gap:5px;flex-wrap:wrap}.block{display:block;color:var(--muted2);margin-top:3px;max-width:280px}.mode{color:var(--accent2);font-weight:700}.cap{display:inline-block;border:1px solid var(--line2);padding:2px 5px;border-radius:3px;font-size:8px}.cap.available{color:var(--accent2);border-color:rgba(255,138,0,.4)}.cap.unavailable{color:var(--muted2)}.radio-note{padding:12px 18px;border-bottom:1px solid var(--line);color:var(--muted);font-size:10px}.radio-note strong{color:var(--accent2)}label{display:block;color:var(--muted);font-size:9px;letter-spacing:.05em;margin:0 0 11px}input,select{display:block;width:100%;margin-top:5px;border:1px solid var(--line2);background:#090b0d;color:var(--text);padding:9px 10px;border-radius:4px;outline:none;font:11px var(--mono)}input:focus,select:focus{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-soft)}button{border:1px solid var(--accent);background:var(--accent);color:#160c02;padding:8px 11px;border-radius:4px;font:800 10px var(--mono);cursor:pointer}button:disabled{opacity:.35;cursor:not-allowed}.button-ghost{width:100%;background:transparent;color:var(--muted);border-color:var(--line)}.field-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}.align-end{display:flex;align-items:flex-end;padding-bottom:11px}.terminal-alert{border:1px solid rgba(255,138,0,.35);background:var(--accent-soft);color:var(--accent2);padding:10px 12px;border-radius:5px;margin-bottom:14px}.terminal-alert.error{border-color:rgba(255,93,93,.35);background:var(--danger-soft);color:#ff9b9b}.terminal-alert.warning{color:var(--accent2)}.dim,.subtle{color:var(--muted)}.compact-terminal{min-height:0}.login-shell{display:grid;place-items:center;min-height:100vh;padding:20px}.login-terminal{width:min(520px,100%);border:1px solid var(--line);background:#0b0e11;border-radius:9px;overflow:hidden;box-shadow:0 28px 90px rgba(0,0,0,.45)}.login-content{padding:28px}.login-brand{display:flex;align-items:center;gap:12px;margin-bottom:22px}.boot-lines{font-size:10px;color:var(--muted);margin-bottom:22px}.boot-lines p{margin:4px 0}.terminal-form{margin-top:18px}.terminal-form button{width:100%;margin-top:4px}.login-foot{color:var(--accent);font-size:9px;letter-spacing:.14em;text-align:center;margin:22px 0 0}.key-terminal{width:min(720px,100%)}.token-block{border:1px solid var(--line);background:#080a0c;padding:13px;margin:14px 0}.token-block code{display:block;overflow-wrap:anywhere;margin-bottom:10px}.text-link{color:var(--accent2)}footer{padding:22px 4px 0;color:var(--muted2);font-size:9px;text-align:center}footer span{color:var(--accent)}.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}@media(max-width:1050px){.admin-shell{grid-template-columns:1fr}.sidebar{position:relative;height:auto;border-right:0;border-bottom:1px solid var(--line)}nav{display:flex;gap:4px;flex-wrap:wrap}nav span{width:100%}.sidebar-foot{display:none}.main-grid{grid-template-columns:1fr}.inspector{position:relative;top:auto}.capability-strip{grid-template-columns:1fr}.capability-strip>div{border-right:0;border-bottom:1px solid rgba(255,138,0,.18)}}@media(max-width:700px){.workspace{padding:16px}.workspace-header{align-items:flex-start;gap:12px}.split-grid,.field-grid{grid-template-columns:1fr}.console-pane{border-right:0;border-bottom:1px solid var(--line)}.main-grid{display:block}.inspector{margin-top:14px}.terminal-body{min-height:260px}.capability-strip{display:block}}
</style>"""
