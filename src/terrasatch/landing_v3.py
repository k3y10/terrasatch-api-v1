"""Fleet-scaled TerraListen public console built on the live radio surface."""

from __future__ import annotations

from terrasatch.landing_v2 import build_landing_page as build_base_landing_page

_OLD_FLEET = '''<section class="card"><div class="title"><span>REGISTERED EDGE</span><b id="fleet-badge">PRIVATE</b></div><div class="rows"><div class="row"><span>Fleet</span><b id="fleet-summary" class="health unknown">ADMIN SIGN-IN</b></div><div class="row"><span>Device</span><b id="fleet-device">—</b></div><div class="row"><span>Hardware</span><b id="fleet-hardware">—</b></div><div class="row"><span>RX</span><b id="fleet-rx">—</b></div><div class="row"><span>TX</span><b id="fleet-tx">—</b></div><div class="row"><span>Mode</span><b id="fleet-mode">—</b></div></div><div class="fleet-detail" id="fleet-detail">Registered device state is session-protected. Sign into Admin to show heartbeat age, reported hardware, RX/TX capabilities and current Satchy policy.</div></section>'''

_NEW_FLEET = '''<section class="card fleet-card"><div class="title"><span>REGISTERED EDGE FLEET</span><b id="fleet-badge">PRIVATE</b></div><div class="fleet-metrics"><div><span>ONLINE</span><b id="fleet-summary" class="health unknown">ADMIN SIGN-IN</b></div><div><span>SITES</span><b id="fleet-sites">—</b></div><div><span>RX READY</span><b id="fleet-rx-count">—</b></div><div><span>TX READY</span><b id="fleet-tx-count">—</b></div><div><span>ATTENTION</span><b id="fleet-attention" class="health unknown">—</b></div></div><div class="fleet-primary"><small>PRIORITY EDGE</small><div class="row"><span>Device</span><b id="fleet-device">—</b></div><div class="row"><span>Radio hardware</span><b id="fleet-hardware">—</b></div><div class="row"><span>RX</span><b id="fleet-rx">—</b></div><div class="row"><span>TX</span><b id="fleet-tx">—</b></div><div class="row"><span>Mode</span><b id="fleet-mode">—</b></div></div><div class="fleet-detail" id="fleet-detail">Registered fleet state is session-protected. Sign into Admin or the organization portal to show tenant-scoped heartbeat and capability data.</div><div class="fleet-links"><a href="/admin">SUPERADMIN FLEET</a><a href="/portal">ORGANIZATION PORTAL</a></div></section>'''

_EXTRA_STYLE = '''<style>
.fleet-metrics{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1px;background:var(--l);border-bottom:1px solid var(--l)}.fleet-metrics>div{background:var(--p2);padding:8px 10px;min-width:0}.fleet-metrics span,.fleet-primary>small{display:block;color:var(--m2);font:800 7px var(--mono);letter-spacing:.08em}.fleet-metrics b{display:block;margin-top:4px;font-size:9px;overflow-wrap:anywhere}.fleet-primary{padding:8px 0 2px;border-bottom:1px solid var(--l)}.fleet-primary>small{padding:0 13px 3px}.fleet-primary .row{padding-top:4px;padding-bottom:4px}.fleet-links{display:grid;grid-template-columns:1fr 1fr;border-top:1px solid var(--l)}.fleet-links a{padding:8px 10px;text-align:center;color:var(--m);text-decoration:none;font:800 7px var(--mono);letter-spacing:.06em}.fleet-links a+a{border-left:1px solid var(--l)}.fleet-links a:hover{color:var(--o2);background:var(--os)}
</style>'''

_EXTRA_SCRIPT = '''<script>
(()=>{const q=id=>document.getElementById(id);async function refreshFleetSummary(){try{const r=await fetch('/admin/fleet-status',{cache:'no-store',credentials:'same-origin'});if(!r.ok)return;const p=await r.json(),s=p.summary||{};const set=(id,value,cls='')=>{const el=q(id);if(!el)return;el.textContent=String(value);if(cls)el.className=cls};set('fleet-sites',s.sites||0);set('fleet-rx-count',s.rx_capable||0,(s.rx_capable||0)?'green':'');set('fleet-tx-count',s.tx_capable||0,(s.tx_capable||0)?'yellow':'');const attention=s.attention||0;set('fleet-attention',attention,`health ${attention?'degraded':'healthy'}`)}catch(_){}}refreshFleetSummary();setInterval(refreshFleetSummary,10000)})();
</script>'''


def build_landing_page(*, environment: str, deployment: str, version: str, docs_enabled: bool) -> str:
    html = build_base_landing_page(
        environment=environment,
        deployment=deployment,
        version=version,
        docs_enabled=docs_enabled,
    )
    html = html.replace(_OLD_FLEET, _NEW_FLEET, 1)
    html = html.replace('<a href="/admin">Admin</a>', '<a href="/portal">Portal</a><a href="/admin">Admin</a>', 1)
    html = html.replace("</head>", _EXTRA_STYLE + "</head>", 1)
    html = html.replace("</body>", _EXTRA_SCRIPT + "</body>", 1)
    return html
