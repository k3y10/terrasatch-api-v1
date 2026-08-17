"""Satchy-aware extension of the TerraSatch admin dashboard renderer."""
# ruff: noqa: E501

from __future__ import annotations

from html import escape

from terrasatch.admin.ai_channel import ai_channel_config
from terrasatch.admin.device_status import device_status_payload
from terrasatch.admin.ui import render_dashboard as render_base_dashboard


def _attr(value: object) -> str:
    return escape(str(value), quote=True)


def _age_label(age_seconds: object) -> str:
    if age_seconds is None:
        return "never"
    age = int(age_seconds)
    if age < 60:
        return f"{age}s ago"
    if age < 3600:
        return f"{age // 60}m ago"
    return f"{age // 3600}h ago"


def _fleet_row(device: object) -> str:
    payload = device_status_payload(device)
    health = escape(str(payload["health"]))
    rx = "ON" if payload["rx_enabled"] else "READY" if payload["rx_supported"] else "N/A"
    tx = "ARMED" if payload["tx_enabled"] else "READY" if payload["tx_supported"] else "N/A"
    caps = ", ".join(str(item) for item in payload["capabilities"]) or "no capabilities reported"
    return (
        f"<tr data-fleet-device='{_attr(payload['id'])}'>"
        f"<td><span class='fleet-health {health}'><i></i>{health.upper()}</span>"
        f"<small class='block'>{escape(_age_label(payload['age_seconds']))}</small></td>"
        f"<td><strong>{escape(str(payload['name']))}</strong><small class='block'>{escape(str(payload.get('hostname') or ''))}</small></td>"
        f"<td>{escape(str(payload['hardware']))}</td>"
        f"<td><span class='radio-cap {'supported' if payload['rx_supported'] else 'missing'}'>RX {rx}</span></td>"
        f"<td><span class='radio-cap {'armed' if payload['tx_enabled'] else 'supported' if payload['tx_supported'] else 'missing'}'>TX {tx}</span></td>"
        f"<td><span class='mode'>{escape(str(payload['mode']))}</span></td>"
        f"<td><small>{escape(caps)}</small></td>"
        "</tr>"
    )


def render_dashboard(**kwargs: object) -> str:
    html = render_base_dashboard(**kwargs)
    devices = kwargs.get("edge_devices") or []

    fleet_rows = "".join(_fleet_row(device) for device in devices)
    if not fleet_rows:
        fleet_rows = "<tr><td colspan='7' class='dim'>Select an organization, pair an Edge device, then run a heartbeat to populate live health and capabilities.</td></tr>"

    fleet_section = f"""<section id="fleet" class="console-section"><div class="section-heading"><div><small>// EDGE FLEET</small><h2>Registered device health</h2></div><span class="section-index">03</span></div>
<div class="radio-note"><strong>Heartbeat-backed state.</strong> A registered Edge updates <code>last_seen_at</code>, hardware inventory and RX/TX capabilities whenever it sends <code>/api/v1/edge/heartbeat</code>. Online/stale/offline colors come from heartbeat age, not branding.</div>
<div class="fleet-summary" id="fleet-summary-line"><span><i class="fleet-dot online"></i>online ≤ 2m</span><span><i class="fleet-dot stale"></i>stale ≤ 15m</span><span><i class="fleet-dot offline"></i>offline &gt; 15m</span><span><i class="fleet-dot never"></i>never reported</span></div>
<div class="table-wrap"><table><thead><tr><th>Health</th><th>Device</th><th>Hardware / provider</th><th>Receive</th><th>Transmit</th><th>Mode</th><th>Reported capabilities</th></tr></thead><tbody id="edge-fleet-body">{fleet_rows}</tbody></table></div></section>"""

    rows: list[str] = []
    for device in devices:
        ai = ai_channel_config(device)
        binding = ai.get("provider_channel") or ai.get("frequency_hz") or "not bound"
        rows.append(
            f"<tr><td><code>{escape(str(device.id))}</code></td>"
            f"<td><strong class='satchy-name'>{escape(str(ai.get('agent_name') or 'Satchy'))}</strong><small class='block'>{escape(str(ai.get('name') or 'Satchy AI Channel'))}</small></td>"
            f"<td>{escape(str(ai.get('activation_phrase') or 'TerraSatch'))}</td>"
            f"<td><code>{escape(str(ai.get('logical_channel_id') or 'not bound'))}</code></td>"
            f"<td>{escape(str(binding))}</td><td>{escape(str(ai.get('reply_route') or 'dashboard'))}</td>"
            f"<td class='actions'><button type='button' class='mini' data-prefill='edge ai {_attr(device.id)} show'>show</button>"
            f"<button type='button' class='mini' data-prefill='edge ai {_attr(device.id)} bind &lt;channel_uuid&gt;'>bind</button>"
            f"<button type='button' class='mini' data-prefill='edge ai {_attr(device.id)} trigger TerraSatch'>trigger</button></td></tr>"
        )
    body = (
        "".join(rows)
        or "<tr><td colspan='7' class='dim'>Pair and sync an Edge device to configure its Satchy AI channel.</td></tr>"
    )
    satchy_section = f"""<section id="satchy" class="console-section"><div class="section-heading"><div><small>// AI RADIO</small><h2>Satchy AI Channel</h2></div><span class="section-index">04</span></div>
<div class="radio-note"><strong>Logical first, provider bound.</strong> Satchy is the TerraListen AI agent. Bind the logical channel to each site's approved provider channel/frequency. Reply routes are policy; RF requires a TX-capable provider plus explicit TX policy.</div>
<div class="table-wrap"><table><thead><tr><th>Edge</th><th>Agent</th><th>Trigger</th><th>Logical channel</th><th>Provider binding</th><th>Reply</th><th>Configure</th></tr></thead><tbody>{body}</tbody></table></div>
<div class="console-pane"><div class="command-help"><small>QUICK START</small><code>agent create &lt;site_uuid&gt; Satchy</code><code>channel create &lt;site_uuid&gt; "Satchy AI Channel" --agent &lt;agent_uuid&gt;</code><code>edge ai &lt;device_uuid&gt; bind &lt;channel_uuid&gt;</code><code>edge ai &lt;device_uuid&gt; provider-channel "Operations 2"</code><code>edge ai &lt;device_uuid&gt; frequency &lt;authorized_hz&gt;</code><code>edge ai &lt;device_uuid&gt; reply dashboard</code></div></div></section>"""

    html = html.replace(
        '<a href="#radio">› Radio capability</a>',
        '<a href="#radio">› Radio capability</a><a href="#fleet">› Registered Edge health</a><a href="#satchy">› Satchy AI channel</a>',
        1,
    )
    radio_marker = '<section id="radio" class="console-section">'
    if radio_marker in html:
        html = html.replace(radio_marker, fleet_section + radio_marker, 1)
    key_marker = '<section id="keys" class="console-section">'
    if key_marker in html:
        html = html.replace(key_marker, satchy_section + key_marker, 1)

    extra_styles = """<style>
:root{--fleet-green:#6ee7a0;--fleet-yellow:#f6c65b;--fleet-red:#ff6b6b;--fleet-blue:#72b7ff}.fleet-summary{display:flex;flex-wrap:wrap;gap:16px;padding:10px 18px;border-bottom:1px solid var(--line);color:var(--muted);font-size:9px}.fleet-summary span{display:flex;align-items:center;gap:6px}.fleet-dot,.fleet-health i{display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--muted2)}.fleet-dot.online,.fleet-health.online i{background:var(--fleet-green);box-shadow:0 0 9px rgba(110,231,160,.45)}.fleet-dot.stale,.fleet-health.stale i{background:var(--fleet-yellow);box-shadow:0 0 9px rgba(246,198,91,.35)}.fleet-dot.offline,.fleet-health.offline i{background:var(--fleet-red);box-shadow:0 0 9px rgba(255,107,107,.35)}.fleet-dot.never,.fleet-health.never i,.fleet-health.disabled i{background:var(--muted2)}.fleet-health{display:inline-flex;align-items:center;gap:6px;font-size:9px;font-weight:800;letter-spacing:.05em;color:var(--muted)}.fleet-health.online{color:var(--fleet-green)}.fleet-health.stale{color:var(--fleet-yellow)}.fleet-health.offline{color:var(--fleet-red)}.fleet-health.online i{animation:fleetPulse 1.7s ease-out infinite}.radio-cap{display:inline-flex;padding:4px 6px;border:1px solid var(--line2);border-radius:4px;font-size:9px;color:var(--muted)}.radio-cap.supported{color:var(--fleet-green);border-color:rgba(110,231,160,.25)}.radio-cap.armed{color:var(--fleet-yellow);border-color:rgba(246,198,91,.28);background:rgba(246,198,91,.06)}.radio-cap.missing{color:var(--muted2)}@keyframes fleetPulse{0%{box-shadow:0 0 0 0 rgba(110,231,160,.4)}70%,100%{box-shadow:0 0 0 7px rgba(110,231,160,0)}}
</style>"""
    html = html.replace("</head>", extra_styles + "</head>", 1)

    live_script = """<script>
(()=>{const body=document.getElementById('edge-fleet-body'),org=document.getElementById('console-org')?.value||'';if(!body)return;const text=(cell,value)=>{cell.textContent=value==null?'—':String(value)};const age=value=>value==null?'never':value<60?`${value}s ago`:value<3600?`${Math.floor(value/60)}m ago`:`${Math.floor(value/3600)}h ago`;const td=()=>document.createElement('td');const small=value=>{const el=document.createElement('small');el.textContent=value;return el};function render(devices){body.replaceChildren();if(!devices.length){const row=document.createElement('tr'),cell=td();cell.colSpan=7;cell.className='dim';cell.textContent='No registered Edge devices for this organization.';row.appendChild(cell);body.appendChild(row);return}for(const device of devices){const row=document.createElement('tr');row.dataset.fleetDevice=device.id;const health=td(),healthLabel=document.createElement('span');healthLabel.className=`fleet-health ${device.health||'never'}`;healthLabel.appendChild(document.createElement('i'));healthLabel.append(String(device.health||'never').toUpperCase());health.appendChild(healthLabel);health.appendChild(small(age(device.age_seconds)));row.appendChild(health);const name=td(),strong=document.createElement('strong');text(strong,device.name);name.appendChild(strong);name.appendChild(small(device.hostname||''));row.appendChild(name);const hardware=td();text(hardware,device.hardware);row.appendChild(hardware);for(const side of ['rx','tx']){const cell=td(),badge=document.createElement('span'),supported=device[`${side}_supported`],enabled=device[`${side}_enabled`];badge.className=`radio-cap ${enabled&&side==='tx'?'armed':supported?'supported':'missing'}`;badge.textContent=`${side.toUpperCase()} ${supported?(enabled?(side==='tx'?'ARMED':'ON'):'READY'):'N/A'}`;cell.appendChild(badge);row.appendChild(cell)}const mode=td(),modeSpan=document.createElement('span');modeSpan.className='mode';text(modeSpan,device.mode);mode.appendChild(modeSpan);row.appendChild(mode);const caps=td();caps.appendChild(small((device.capabilities||[]).join(', ')||'no capabilities reported'));row.appendChild(caps);body.appendChild(row)}}async function refresh(){const query=org?`?organization=${encodeURIComponent(org)}`:'';try{const response=await fetch(`/admin/fleet-status${query}`,{cache:'no-store',credentials:'same-origin'});if(!response.ok)return;const data=await response.json();render(data.devices||[])}catch(_){}}refresh();setInterval(refresh,10000)})();
</script>"""
    html = html.replace("</body>", live_script + "</body>", 1)
    return html
