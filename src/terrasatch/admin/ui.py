"""Terminal-inspired HTML renderers for the TerraSatch admin browser surfaces."""
# ruff: noqa: E501

from __future__ import annotations

from html import escape

from terrasatch.brand import SASQUATCH_ASSET_URL


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
<section class="login-content">
<div class="login-brand"><img src="{escape(SASQUATCH_ASSET_URL)}" alt="TerraSatch Sasquatch"><div><strong>TERRASATCH</strong><small>ADMIN CONSOLE</small></div></div>
<div class="boot-lines" aria-hidden="true"><p><span class="prompt">ts-admin@terrasatch:~$</span> init secure-session</p><p><span class="dim">[ok]</span> TLS endpoint verified</p><p><span class="dim">[ok]</span> session protection armed</p></div>
<h1 id="login-title">Authenticate operator</h1><p class="subtle">Private control-plane access. Session authentication and CSRF protection remain enforced.</p>
{error}<form method="post" action="/admin/login" class="terminal-form"><input type="hidden" name="csrf_token" value="{escape(csrf_token)}">
<label><span>operator@email</span><input required type="email" name="email" autocomplete="username" placeholder="operator@terrasatch.com"></label>
<label><span>password</span><input required type="password" name="password" autocomplete="current-password" placeholder="••••••••••••"></label>
<button type="submit"><span>→</span> establish session</button></form><p class="login-foot">LISTEN. WATCH. LEARN. ADAPT.</p>
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
    sites: list[object],
    csrf_token: str,
    error_message: str | None,
) -> str:
    component_rows = "".join(
        f"<tr><td><span class='status-dot {escape(component.status)}'></span>{escape(component.name)}</td><td class='status-text {escape(component.status)}'>{escape(component.status)}</td><td>{escape(component.detail or '')}</td></tr>"
        for component in components
    )
    component_terminal_lines = "".join(
        f"<p><span class='terminal-key'>{escape(component.name.upper())}</span><span class='terminal-value {escape(component.status)}'>{escape(component.status.upper())}</span><span class='terminal-detail'>{escape(component.detail or '')}</span></p>"
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
        f"<option value='{escape(str(organization.id))}'{' selected' if str(organization.id) == selected_organization else ''}>{escape(organization.name)}</option>"
        for organization in organizations
    )
    org_terminal_rows = "".join(
        f"<p><span class='terminal-id'>{escape(str(organization.id))}</span><span>{escape(organization.name)}</span></p>"
        for organization in organizations
    ) or "<p><span class='dim'>no organizations available</span></p>"
    site_rows = "".join(f"<li><span class='tree-mark'>└─</span>{escape(site.name)}</li>" for site in sites) or "<li><span class='tree-mark'>└─</span>none</li>"
    site_terminal_rows = "".join(f"<p><span class='terminal-id'>{escape(str(site.id))}</span><span>{escape(site.name)}</span></p>" for site in sites) or "<p><span class='dim'>no sites loaded</span></p>"
    error_box = f"<div class='terminal-alert error'><span>error:</span> {escape(error_message)}</div>" if error_message else ""
    status_upper = escape(report_status.upper())
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#08090b"><title>TerraSatch Admin Console</title>{_styles()}</head><body>
<div class="admin-shell"><aside class="sidebar"><a class="brand" href="/admin"><img src="{escape(SASQUATCH_ASSET_URL)}" alt=""><span><strong>TERRASATCH</strong><small>ADMIN CONSOLE</small></span></a>
<div class="sidebar-status"><span class="status-dot {escape(report_status)}"></span><div><small>SYSTEM STATUS</small><strong>{status_upper}</strong></div></div>
<nav aria-label="Admin console"><span>OPERATIONS</span><a href="#terminal">› Console</a><a href="#system">› System status</a><a href="#tenant">› Organizations & sites</a><a href="/admin/edge/pair">› Edge pairing</a><span>ACCESS</span><a href="#keys">› API keys</a><a href="#reference">› API reference</a><a href="/docs">› OpenAPI docs</a></nav>
<div class="sidebar-foot"><small>CONTROL PLANE</small><p>api.terrasatch.com</p><form id="logout-form" method="post" action="/admin/logout"><input type="hidden" name="csrf_token" value="{escape(csrf_token)}"><button class="button-ghost" type="submit">logout</button></form></div></aside>
<main class="workspace"><header class="workspace-header"><div><p class="shell-path">ts-admin@terrasatch:<span>~</span>$</p><h1>Operations Console</h1></div><div class="connection"><span class="status-dot {escape(report_status)}"></span>{status_upper}</div></header>{error_box}
<section id="terminal" class="terminal-window" aria-label="Operator command console"><div class="terminal-chrome"><span></span><span></span><span></span><b>terrasatch-control-plane — operator session</b></div>
<div class="terminal-body" id="terminal-output" aria-live="polite"><p><span class="prompt">ts-admin@terrasatch:~$</span> system status</p><p><span class="terminal-key">STATUS</span><span class="terminal-value {escape(report_status)}">{status_upper}</span></p>{component_terminal_lines}<p class="terminal-spacer"></p><p><span class="prompt">ts-admin@terrasatch:~$</span> tenant current</p><p><span class="terminal-key">ORG</span><span>{escape(selected_name)}</span></p><p><span class="terminal-key">SITES</span><span>{len(sites)}</span></p></div>
<form id="terminal-form" class="command-line" autocomplete="off"><label for="terminal-command" class="sr-only">Admin console command</label><span class="prompt">ts-admin@terrasatch:~$</span><input id="terminal-command" name="command" spellcheck="false" placeholder="type help" aria-describedby="terminal-hint"></form>
<div class="terminal-actions" id="terminal-hint"><button type="button" data-command="status">system status</button><button type="button" data-command="tenant">tenant current</button><button type="button" data-command="organizations">organizations list</button><button type="button" data-command="sites">sites list</button><button type="button" data-command="edge">edge pair</button><button type="button" data-command="api">api reference</button><button type="button" data-command="clear">clear</button></div>
<div class="terminal-note"><span>SAFE CONSOLE</span> Browser commands are navigation/operator shortcuts only. No arbitrary server shell is exposed.</div></section>
<section id="system" class="console-section"><div class="section-heading"><div><small>// SYSTEM</small><h2>Live components</h2></div><span class="section-index">01</span></div><div class="table-wrap"><table><thead><tr><th>Component</th><th>Status</th><th>Detail</th></tr></thead><tbody>{component_rows}</tbody></table></div></section>
<section id="tenant" class="console-section"><div class="section-heading"><div><small>// TENANCY</small><h2>Organizations & sites</h2></div><span class="section-index">02</span></div><div class="split-grid"><div class="console-pane"><h3>tenant current</h3><form method="get" action="/admin"><label>Organization<select name="organization" onchange="this.form.submit()"><option value="">Select organization</option>{organization_options}</select></label></form><div class="tree"><strong>{escape(selected_name)}</strong><ul>{site_rows}</ul></div></div>
<div class="console-pane"><h3>tenant create</h3><form method="post" action="/admin/organizations"><input type="hidden" name="csrf_token" value="{escape(csrf_token)}"><label>Name<input required name="name" placeholder="Organization name"></label><button type="submit">create organization</button></form><form method="post" action="/admin/sites" class="form-divider"><input type="hidden" name="csrf_token" value="{escape(csrf_token)}"><input type="hidden" name="organization" value="{escape(selected_organization)}"><label>Site name<input required name="name" placeholder="Site name" {'disabled' if not selected_organization else ''}></label><button type="submit" {'disabled' if not selected_organization else ''}>create site</button></form></div></div>
<div class="data-terminal"><div><p><span class="prompt">$</span> organizations list</p>{org_terminal_rows}</div><div><p><span class="prompt">$</span> sites list</p>{site_terminal_rows}</div></div></section>
<section id="keys" class="console-section"><div class="section-heading"><div><small>// ACCESS</small><h2>Issue server API key</h2></div><span class="section-index">03</span></div><div class="console-pane key-pane"><p class="subtle">Credentials remain organization-scoped. The selected organization is resolved server-side and the generated token is shown once.</p><form method="post" action="/admin/api-keys"><input type="hidden" name="csrf_token" value="{escape(csrf_token)}"><input type="hidden" name="organization" value="{escape(selected_organization)}"><div class="field-grid"><label>Label<input required name="name" placeholder="edge-node-prod" {'disabled' if not selected_organization else ''}></label><label>Scopes<input name="scope" value="read:events" {'disabled' if not selected_organization else ''}></label></div><button type="submit" {'disabled' if not selected_organization else ''}>issue credential</button></form></div></section>
<section id="reference" class="console-section"><div class="section-heading"><div><small>// REFERENCE</small><h2>Implemented API</h2></div><span class="section-index">04</span></div><div class="table-wrap"><table><thead><tr><th>Method</th><th>Path</th><th>Authorization</th><th>Purpose</th></tr></thead><tbody>{endpoint_rows}</tbody></table></div></section>
<section id="responses" class="console-section"><div class="section-heading"><div><small>// RESPONSES</small><h2>Common responses</h2></div><span class="section-index">05</span></div><div class="table-wrap"><table><thead><tr><th>HTTP</th><th>Code</th><th>Meaning</th></tr></thead><tbody>{error_rows}</tbody></table></div></section>
<footer>TerraSatch Admin Console <span>•</span> LISTEN. WATCH. LEARN. ADAPT.</footer></main></div>{_terminal_script()}</body></html>"""


def render_one_time_key(token: str, organization: str) -> str:
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#08090b"><title>TerraSatch API Key</title>{_styles()}</head>
<body class="login-shell"><main class="login-terminal key-terminal"><div class="terminal-chrome"><span></span><span></span><span></span><b>credential issuance — one time output</b></div><section class="login-content">
<div class="login-brand"><img src="{escape(SASQUATCH_ASSET_URL)}" alt=""><div><strong>TERRASATCH</strong><small>ADMIN CONSOLE</small></div></div><p><span class="prompt">ts-admin@terrasatch:~$</span> api-key issue</p><h1>Credential generated</h1>
<div class="terminal-alert warning"><span>warning:</span> this token is shown only in this response. Store it in a server-side secret manager.</div><div class="token-block"><code id="issued-token">{escape(token)}</code><button type="button" onclick="navigator.clipboard.writeText(document.getElementById('issued-token').textContent)">copy token</button></div>
<p><a class="text-link" href="/admin?organization={escape(organization)}">← return to operations console</a></p></section></main></body></html>"""


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
        f'<option value="{escape(str(org.id))}" {"selected" if str(org.id) == selected_org else ""}>{escape(org.name)}</option>'
        for org in organizations
    )
    site_options = "".join(
        f'<option value="{escape(str(site.id))}">{escape(site.name)}</option>'
        for site in sites
    )
    message = ""
    if approved:
        message = f'<div class="terminal-alert"><span>[approved]</span> device pairing <strong>{escape(approved)}</strong> is ready for credential claim.</div>'
    elif error:
        message = f'<div class="terminal-alert error"><span>[error]</span> {escape(error)}</div>'
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#08090b"><title>TerraSatch Edge Pairing</title>{_styles()}</head>
<body><div class="admin-shell"><aside class="sidebar"><a class="brand" href="/admin"><img src="{escape(SASQUATCH_ASSET_URL)}" alt=""><span><strong>TERRASATCH</strong><small>ADMIN CONSOLE</small></span></a><nav><span>OPERATIONS</span><a href="/admin">‹ Operations console</a><a href="/admin/edge/pair">› Edge pairing</a></nav><div class="sidebar-foot"><small>RECEIVE-ONLY EDGE</small><p>Controlled field enrollment</p></div></aside>
<main class="workspace"><header class="workspace-header"><div><p class="shell-path">ts-admin@terrasatch:<span>~</span>$ edge pair</p><h1>Approve TerraSatch Edge</h1></div><div class="connection"><span class="status-dot healthy"></span>SECURE SESSION</div></header>{message}
<section class="terminal-window"><div class="terminal-chrome"><span></span><span></span><span></span><b>pairing workflow</b></div><div class="terminal-body compact-terminal"><p><span class="prompt">ts-admin@terrasatch:~$</span> pairing verify --code {escape(code or 'ABCD-2345')}</p><p class="subtle">Match the code shown by the field computer, load its organization sites, then approve the device.</p></div></section>
<section class="console-section"><div class="section-heading"><div><small>// EDGE</small><h2>Pair field receiver</h2></div><span class="section-index">01</span></div><div class="split-grid"><div class="console-pane"><h3>load destination</h3><form method="get" action="/admin/edge/pair"><label>Pairing code<input name="code" value="{escape(code)}" placeholder="ABCD-2345" required></label><label>Organization<select name="organization" required><option value="">Select organization</option>{org_options}</select></label><button type="submit">load sites</button></form></div>
<div class="console-pane"><h3>approve device</h3><form method="post" action="/admin/edge/pair"><input type="hidden" name="csrf_token" value="{escape(csrf_token)}"><input type="hidden" name="organization" value="{escape(selected_org)}"><label>Pairing code<input name="code" value="{escape(code)}" required></label><label>Site<select name="site_id" required><option value="">Select site</option>{site_options}</select></label><button type="submit" {"disabled" if not sites else ""}>approve pairing</button></form></div></div></section>
<footer>TerraSatch Edge <span>•</span> controlled field enrollment</footer></main></div></body></html>"""


def _terminal_script() -> str:
    return """<script>
(() => {
 const form=document.getElementById('terminal-form'),input=document.getElementById('terminal-command'),output=document.getElementById('terminal-output');if(!form||!input||!output)return;
 const history=[];let cursor=0;const write=(text,cls='')=>{const line=document.createElement('p');if(cls)line.className=cls;line.textContent=text;output.appendChild(line);output.scrollTop=output.scrollHeight};
 const go=(selector)=>{const target=document.querySelector(selector);if(target)target.scrollIntoView({behavior:'smooth',block:'start'})};
 const run=(raw)=>{const command=raw.trim().toLowerCase();if(!command)return;write(`ts-admin@terrasatch:~$ ${raw}`,'echo-command');history.push(raw);cursor=history.length;
 const actions={'help':()=>write('commands: status, tenant, organizations, sites, edge, api, keys, docs, clear, logout'),'status':()=>{write('opening system status');go('#system')},'system status':()=>{write('opening system status');go('#system')},'tenant':()=>{write('opening tenant context');go('#tenant')},'tenant current':()=>{write('opening tenant context');go('#tenant')},'organizations':()=>{write('opening organizations');go('#tenant')},'organizations list':()=>{write('opening organizations');go('#tenant')},'sites':()=>{write('opening sites');go('#tenant')},'sites list':()=>{write('opening sites');go('#tenant')},'keys':()=>{write('opening API key issuance');go('#keys')},'key':()=>{write('opening API key issuance');go('#keys')},'api':()=>{write('opening API reference');go('#reference')},'api reference':()=>{write('opening API reference');go('#reference')},'docs':()=>window.location.assign('/docs'),'edge':()=>window.location.assign('/admin/edge/pair'),'edge pair':()=>window.location.assign('/admin/edge/pair'),'logout':()=>{const logout=document.getElementById('logout-form');if(logout)logout.submit()},'clear':()=>output.replaceChildren(),'cls':()=>output.replaceChildren()};
 const action=actions[command];if(action)action();else write(`command not found: ${command}. type 'help'.`,'terminal-error-line')};
 form.addEventListener('submit',event=>{event.preventDefault();const value=input.value;input.value='';run(value)});document.querySelectorAll('[data-command]').forEach(button=>button.addEventListener('click',()=>run(button.dataset.command||'')));
 input.addEventListener('keydown',event=>{if(event.key==='ArrowUp'){event.preventDefault();cursor=Math.max(0,cursor-1);input.value=history[cursor]||''}else if(event.key==='ArrowDown'){event.preventDefault();cursor=Math.min(history.length,cursor+1);input.value=history[cursor]||''}else if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='l'){event.preventDefault();output.replaceChildren()}});
})();
</script>"""


def _styles() -> str:
    return """<style>
:root{--bg:#08090b;--panel:#0e1115;--line:#262b31;--line2:#353b42;--text:#e7e9ec;--muted:#8c949e;--muted2:#626a73;--accent:#ff8a00;--accent2:#ffb15c;--accent-soft:rgba(255,138,0,.12);--danger:#ff5d5d;--danger-soft:rgba(255,93,93,.10);--radius:10px;--mono:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,"Liberation Mono","Courier New",monospace}*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:radial-gradient(circle at 82% -10%,rgba(255,138,0,.08),transparent 30%),var(--bg);color:var(--text);font:14px/1.55 var(--mono);min-height:100vh}body:before{content:"";position:fixed;inset:0;pointer-events:none;opacity:.16;background-image:linear-gradient(rgba(255,255,255,.018) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.014) 1px,transparent 1px);background-size:24px 24px}a{color:inherit}button,input,select{font:inherit}.admin-shell{display:grid;grid-template-columns:238px minmax(0,1fr);min-height:100vh}.sidebar{position:sticky;top:0;height:100vh;border-right:1px solid var(--line);background:rgba(8,9,11,.96);padding:20px 16px;display:flex;flex-direction:column;z-index:3}.brand{display:flex;align-items:center;gap:11px;text-decoration:none;padding:4px 5px 18px;border-bottom:1px solid var(--line)}.brand img,.login-brand img{width:42px;height:42px;object-fit:contain}.brand strong,.login-brand strong{display:block;font-size:14px;letter-spacing:.08em}.brand small,.login-brand small{display:block;color:var(--accent);font-size:10px;letter-spacing:.12em;margin-top:2px}.sidebar-status{display:flex;align-items:center;gap:10px;padding:16px 5px;border-bottom:1px solid var(--line)}.sidebar-status small{display:block;color:var(--muted);font-size:9px;letter-spacing:.12em}.sidebar-status strong{display:block;margin-top:3px;font-size:11px;color:var(--accent2)}.status-dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--muted2);box-shadow:0 0 0 3px rgba(255,255,255,.03);margin-right:9px}.status-dot.healthy,.status-dot.pass,.status-dot.ready,.status-dot.ok{background:var(--accent);box-shadow:0 0 12px rgba(255,138,0,.55)}.status-dot.unhealthy,.status-dot.degraded,.status-dot.error,.status-dot.fail{background:var(--danger);box-shadow:0 0 12px rgba(255,93,93,.45)}nav{padding:14px 0;overflow:auto}nav span{display:block;color:var(--muted2);font-size:9px;letter-spacing:.16em;padding:14px 8px 6px}nav a{display:block;text-decoration:none;color:#b8bec6;padding:7px 9px;border-radius:6px;font-size:12px}nav a:hover,nav a:focus-visible{background:var(--accent-soft);color:var(--accent2);outline:none}.sidebar-foot{margin-top:auto;border-top:1px solid var(--line);padding:14px 5px 2px}.sidebar-foot small{color:var(--muted2);font-size:9px;letter-spacing:.14em}.sidebar-foot p{margin:5px 0 10px;color:var(--muted);font-size:11px}.workspace{min-width:0;padding:24px 30px 34px;max-width:1500px;width:100%;margin:0 auto}.workspace-header{display:flex;justify-content:space-between;align-items:flex-end;padding:2px 2px 20px;border-bottom:1px solid var(--line);margin-bottom:20px}.shell-path{margin:0 0 4px;color:var(--accent);font-size:11px}.shell-path span{color:var(--accent2)}h1,h2,h3,p{margin-top:0}h1{margin-bottom:0;font-size:22px;letter-spacing:-.03em;font-weight:650}h2{font-size:17px;margin-bottom:0}h3{font-size:12px;text-transform:uppercase;letter-spacing:.08em;color:var(--accent2)}.connection{border:1px solid rgba(255,138,0,.35);background:var(--accent-soft);color:var(--accent2);padding:7px 10px;border-radius:6px;font-size:10px;letter-spacing:.1em}.connection .status-dot{margin-right:5px}.terminal-window,.console-section{border:1px solid var(--line);background:rgba(11,13,16,.92);border-radius:var(--radius);overflow:hidden}.terminal-window{margin-bottom:18px;box-shadow:0 20px 70px rgba(0,0,0,.28)}.terminal-chrome{height:36px;display:flex;align-items:center;gap:6px;padding:0 12px;border-bottom:1px solid var(--line);background:#0b0d10}.terminal-chrome>span{width:8px;height:8px;border-radius:50%;background:#30353b}.terminal-chrome>span:first-child{background:#65320e}.terminal-chrome>span:nth-child(2){background:#7c4b17}.terminal-chrome>span:nth-child(3){background:#9c611c}.terminal-chrome b{font-weight:500;color:var(--muted);font-size:10px;margin-left:6px}.terminal-body{padding:20px 20px 12px;min-height:280px;max-height:480px;overflow:auto;font-size:12px}.compact-terminal{min-height:0}.terminal-body p,.data-terminal p{margin:0 0 5px}.prompt{color:var(--accent);font-weight:700}.terminal-key{display:inline-block;width:110px;color:#c7ccd2}.terminal-value{display:inline-block;min-width:96px;color:var(--accent2);font-weight:700}.terminal-value.unhealthy,.terminal-value.degraded,.terminal-value.error,.terminal-value.fail{color:var(--danger)}.terminal-detail{color:var(--muted)}.terminal-spacer{height:8px}.terminal-id{display:inline-block;min-width:310px;color:var(--muted);overflow:hidden;text-overflow:ellipsis;vertical-align:bottom}.dim{color:var(--muted2)}.command-line{display:flex;align-items:center;gap:10px;border-top:1px solid var(--line);padding:12px 20px;background:#090b0d}.command-line input{flex:1;border:0;outline:0;background:transparent;color:var(--text);min-width:0;padding:4px}.command-line input::placeholder{color:#4e555d}.terminal-actions{display:flex;flex-wrap:wrap;gap:7px;padding:10px 20px 12px;border-top:1px solid #171b1f}.terminal-actions button{margin:0;padding:6px 9px;border:1px solid var(--line);background:#0d1013;color:var(--muted);border-radius:5px;font-size:10px;cursor:pointer}.terminal-actions button:hover{border-color:rgba(255,138,0,.45);color:var(--accent2)}.terminal-note{border-top:1px solid var(--line);padding:9px 20px;color:var(--muted2);font-size:9px;letter-spacing:.04em}.terminal-note span{color:var(--accent);margin-right:8px}.echo-command{color:#cdd1d6}.terminal-error-line{color:var(--danger)}.console-section{margin:18px 0}.section-heading{display:flex;align-items:flex-start;justify-content:space-between;padding:17px 20px;border-bottom:1px solid var(--line)}.section-heading small{display:block;color:var(--accent);font-size:9px;letter-spacing:.16em;margin-bottom:3px}.section-index{color:#383e45;font-size:22px;font-weight:700}.table-wrap{overflow:auto}table{border-collapse:collapse;width:100%;min-width:700px;font-size:11px}th,td{text-align:left;padding:10px 16px;border-top:1px solid #1b1f24;vertical-align:top}thead th{border-top:0;background:#0b0e11;color:var(--muted2);font-size:9px;letter-spacing:.12em;text-transform:uppercase;font-weight:650}tbody tr:hover{background:rgba(255,138,0,.025)}td code{color:#c7ccd3}.method{color:var(--accent2);font-weight:700}.status-text{color:var(--accent2);text-transform:uppercase;font-size:10px}.status-text.unhealthy,.status-text.degraded,.status-text.error,.status-text.fail{color:var(--danger)}.split-grid{display:grid;grid-template-columns:1fr 1fr}.console-pane{padding:20px;border-right:1px solid var(--line)}.split-grid>.console-pane:last-child{border-right:0}.console-pane form+form{margin-top:20px}.form-divider{padding-top:18px;border-top:1px solid var(--line)}label{display:block;color:var(--muted);font-size:10px;letter-spacing:.06em;margin:0 0 12px}input,select{display:block;width:100%;margin-top:6px;border:1px solid var(--line2);background:#090b0d;color:var(--text);padding:10px 11px;border-radius:5px;outline:none}input:focus,select:focus{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-soft)}input:disabled,select:disabled{opacity:.45}button{border:1px solid var(--accent);background:var(--accent);color:#120a02;padding:9px 12px;border-radius:5px;font-weight:800;font-size:10px;letter-spacing:.04em;cursor:pointer}button:hover{filter:brightness(1.08)}button:disabled{opacity:.35;cursor:not-allowed}.button-ghost{width:100%;background:transparent;color:var(--muted);border-color:var(--line);padding:7px}.button-ghost:hover{color:var(--accent2);border-color:rgba(255,138,0,.45)}.tree{margin-top:14px;border:1px solid var(--line);background:#090b0d;padding:12px;border-radius:6px;font-size:11px}.tree strong{color:var(--accent2)}.tree ul{list-style:none;margin:8px 0 0;padding:0;color:var(--muted)}.tree li{padding:3px 0}.tree-mark{color:#4b525a;margin-right:8px}.data-terminal{display:grid;grid-template-columns:1fr 1fr;border-top:1px solid var(--line);background:#090b0d}.data-terminal>div{padding:14px 20px;min-width:0}.data-terminal>div+div{border-left:1px solid var(--line)}.field-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}.key-pane{border-right:0}.subtle{color:var(--muted);max-width:760px;font-size:11px}.terminal-alert{margin:0 0 18px;padding:10px 12px;border:1px solid var(--line);border-left:3px solid var(--accent);background:#0d1013;color:var(--muted);border-radius:5px;font-size:11px}.terminal-alert span{color:var(--accent2);font-weight:700}.terminal-alert.error{border-left-color:var(--danger);background:var(--danger-soft);color:#e8b7b7}.terminal-alert.error span{color:var(--danger)}.terminal-alert.warning{border-left-color:var(--accent);background:var(--accent-soft)}footer{padding:18px 2px 0;color:#4f565e;font-size:9px;letter-spacing:.08em;text-align:center}footer span{color:var(--accent)}.login-shell{display:grid;place-items:center;padding:24px;background:radial-gradient(circle at 50% -5%,rgba(255,138,0,.12),transparent 35%),#07080a}.login-terminal{width:min(620px,100%);border:1px solid var(--line);border-radius:12px;background:#0b0d10;overflow:hidden;box-shadow:0 30px 110px rgba(0,0,0,.55)}.login-content{padding:34px}.login-brand{display:flex;align-items:center;gap:12px;margin-bottom:26px}.boot-lines{border-left:1px solid #252a30;padding-left:14px;margin-bottom:24px;color:#aab0b7;font-size:10px}.boot-lines p{margin:3px 0}.login-content h1{font-size:20px;margin-bottom:7px}.terminal-form{margin-top:22px}.terminal-form label{margin-bottom:15px}.terminal-form button{width:100%;margin-top:4px}.terminal-form button span{margin-right:5px}.login-foot{text-align:center;color:#4d545c;font-size:9px;letter-spacing:.16em;margin:26px 0 0}.key-terminal{width:min(760px,100%)}.token-block{border:1px solid var(--line);background:#07090b;border-radius:6px;padding:14px;margin:18px 0}.token-block code{display:block;overflow-wrap:anywhere;color:var(--accent2);font-size:11px;margin-bottom:12px}.text-link{color:var(--accent2);text-decoration:none}.text-link:hover{text-decoration:underline}.sr-only{position:absolute!important;width:1px!important;height:1px!important;padding:0!important;margin:-1px!important;overflow:hidden!important;clip:rect(0,0,0,0)!important;white-space:nowrap!important;border:0!important}@media(max-width:920px){.admin-shell{grid-template-columns:1fr}.sidebar{position:relative;height:auto;border-right:0;border-bottom:1px solid var(--line);display:grid;grid-template-columns:1fr auto;gap:10px}.sidebar nav{display:none}.sidebar-status{border:0;padding:8px}.sidebar-foot{display:none}.brand{border:0;padding-bottom:4px}.workspace{padding:20px}.terminal-id{min-width:220px}}@media(max-width:680px){.workspace{padding:14px}.workspace-header{align-items:flex-start;gap:14px}.connection{margin-top:2px}.split-grid,.data-terminal,.field-grid{grid-template-columns:1fr}.console-pane{border-right:0;border-bottom:1px solid var(--line)}.data-terminal>div+div{border-left:0;border-top:1px solid var(--line)}.terminal-body{padding:16px 14px}.command-line,.terminal-actions,.terminal-note{padding-left:14px;padding-right:14px}.terminal-key{width:88px}.terminal-detail{display:block;margin-left:88px}.login-shell{padding:12px}.login-content{padding:24px 20px}.login-brand img{width:38px;height:38px}}
</style>"""
