"""Satchy-aware extension of the existing TerraSatch admin dashboard renderer."""
from __future__ import annotations
from html import escape
from terrasatch.admin.ai_channel import ai_channel_config
from terrasatch.admin.ui import render_dashboard as render_base_dashboard

def _attr(value: object) -> str:
    return escape(str(value), quote=True)

def render_dashboard(**kwargs: object) -> str:
    html = render_base_dashboard(**kwargs)
    devices = kwargs.get("edge_devices") or []
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
    body = "".join(rows) or "<tr><td colspan='7' class='dim'>Pair and sync an Edge device to configure its Satchy AI channel.</td></tr>"
    section = f'''<section id="satchy" class="console-section"><div class="section-heading"><div><small>// AI RADIO</small><h2>Satchy AI Channel</h2></div><span class="section-index">04</span></div>
<div class="radio-note"><strong>Logical first, provider bound.</strong> Satchy is the TerraListen AI agent. Bind the logical channel to each site's approved provider channel/frequency. Reply routes are policy; RF requires a TX-capable provider plus explicit TX policy.</div>
<div class="table-wrap"><table><thead><tr><th>Edge</th><th>Agent</th><th>Trigger</th><th>Logical channel</th><th>Provider binding</th><th>Reply</th><th>Configure</th></tr></thead><tbody>{body}</tbody></table></div>
<div class="console-pane"><div class="command-help"><small>QUICK START</small><code>agent create &lt;site_uuid&gt; Satchy</code><code>channel create &lt;site_uuid&gt; "Satchy AI Channel" --agent &lt;agent_uuid&gt;</code><code>edge ai &lt;device_uuid&gt; bind &lt;channel_uuid&gt;</code><code>edge ai &lt;device_uuid&gt; provider-channel "Operations 2"</code><code>edge ai &lt;device_uuid&gt; frequency &lt;authorized_hz&gt;</code><code>edge ai &lt;device_uuid&gt; reply dashboard</code></div></div></section>'''
    html = html.replace('<a href="#radio">› Radio capability</a>', '<a href="#radio">› Radio capability</a><a href="#satchy">› Satchy AI channel</a>', 1)
    marker = '<section id="keys" class="console-section">'
    if marker in html:
        html = html.replace(marker, section + marker, 1)
    return html
