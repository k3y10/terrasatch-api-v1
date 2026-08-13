"""Lightweight branded landing page for the public TerraSatch API host."""

from __future__ import annotations

from html import escape


_BRAND_LOGO_URL = "/assets/terrasatch-logo.svg"


def build_landing_page(
    *,
    environment: str,
    deployment: str,
    version: str,
    docs_enabled: bool,
) -> str:
    """Return a single-viewport TerraSatch radio console without exposing secrets."""

    docs_key = (
        '<a class="key" href="/docs"><b>F2</b><span>DOCS</span></a>'
        if docs_enabled
        else '<span class="key disabled"><b>F2</b><span>DOCS OFF</span></span>'
    )
    docs_nav = '<a href="/docs">Docs</a>' if docs_enabled else '<span>Docs Off</span>'

    replacements = {
        "__ENVIRONMENT__": escape(environment),
        "__DEPLOYMENT__": escape(deployment),
        "__VERSION__": escape(version),
        "__DOCS_KEY__": docs_key,
        "__DOCS_NAV__": docs_nav,
        "__BRAND_LOGO__": _BRAND_LOGO_URL,
    }

    html = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#080a08">
<meta name="description" content="TerraSatch receive-side field radio intelligence console.">
<title>TerraSatch · Radio Console</title>
<style>
:root{color-scheme:dark;--bg:#070907;--case:#141814;--case2:#0e110e;--text:#f4eddb;--muted:#7e897f;--line:rgba(244,237,219,.13);--orange:#f36b16;--amber:#f3a12a;--green:#9ae4a7;--green2:#4ebc6d;--screen:#08120a}
*{box-sizing:border-box}html,body{width:100%;height:100%;height:100dvh;margin:0;overflow:hidden}body{background:radial-gradient(circle at 50% -15%,rgba(243,107,22,.18),transparent 38%),var(--bg);color:var(--text);font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}body:before{content:"";position:fixed;inset:0;pointer-events:none;opacity:.22;background-image:linear-gradient(rgba(244,237,219,.025) 1px,transparent 1px),linear-gradient(90deg,rgba(244,237,219,.025) 1px,transparent 1px);background-size:28px 28px}.app{height:100vh;height:100dvh;display:grid;grid-template-rows:64px minmax(0,1fr) 36px;width:min(1440px,100%);margin:auto;padding:0 18px;position:relative;z-index:1}.mono{font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace}
header{display:flex;align-items:center;justify-content:space-between;gap:16px;border-bottom:1px solid var(--line);min-width:0}.brand{display:flex;align-items:center;gap:10px;min-width:0;text-decoration:none;color:inherit}.brand img{width:44px;height:44px;object-fit:contain;flex:none}.brand-copy{min-width:0}.brand-copy strong{display:block;font-size:13px;letter-spacing:.12em;white-space:nowrap}.brand-copy span{display:block;margin-top:2px;color:var(--muted);font:700 8px/1.2 ui-monospace,monospace;letter-spacing:.13em;text-transform:uppercase;white-space:nowrap}.state{display:flex;align-items:center;gap:7px;margin-left:auto}.pill{border:1px solid var(--line);padding:6px 8px;border-radius:999px;font:750 8px/1 ui-monospace,monospace;letter-spacing:.1em;text-transform:uppercase;color:#a5aea6;white-space:nowrap}.pill.live{color:var(--green);border-color:rgba(154,228,167,.25)}.pill.live:before{content:"";display:inline-block;width:5px;height:5px;border-radius:50%;background:var(--green);box-shadow:0 0 8px var(--green);margin-right:5px}.nav{display:flex;gap:12px;align-items:center}.nav a,.nav span{color:#9da69e;text-decoration:none;font:700 8px/1 ui-monospace,monospace;text-transform:uppercase;letter-spacing:.08em;white-space:nowrap}.nav a:hover{color:var(--orange)}
main{min-height:0;padding:14px 0;overflow:hidden}.console{height:100%;min-height:0;border:1px solid #292f29;border-radius:20px;background:linear-gradient(145deg,#171b17,#0d100d 72%);box-shadow:0 24px 70px rgba(0,0,0,.42),inset 0 1px rgba(255,255,255,.035);padding:12px;display:grid;grid-template-rows:44px minmax(0,1fr) 54px;gap:10px;position:relative}.console:before,.console:after{content:"";position:absolute;top:9px;width:6px;height:6px;border:1px solid #363d36;background:#070907;border-radius:50%}.console:before{left:10px}.console:after{right:10px}.console-head{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:10px;padding:0 8px}.unit{display:flex;align-items:center;gap:9px;min-width:0}.unit img{width:34px;height:34px;object-fit:contain}.unit strong{display:block;font-size:10px;letter-spacing:.09em}.unit small{display:block;color:#6f786f;font:700 7px/1.2 ui-monospace,monospace;letter-spacing:.11em;margin-top:2px}.mode{text-align:center;color:#6e786f;font:750 8px/1.2 ui-monospace,monospace;letter-spacing:.12em;text-transform:uppercase}.mode b{color:var(--green)}.knobs{display:flex;justify-content:flex-end;gap:8px}.knob{width:34px;height:34px;border-radius:50%;background:radial-gradient(circle at 40% 34%,#303630 0 16%,#171b17 19% 49%,#060806 51% 61%,#262c26 63% 100%);border:1px solid #303730;position:relative;box-shadow:0 5px 10px #0007}.knob:after{content:"";position:absolute;left:16px;top:4px;width:2px;height:8px;background:var(--orange);transform:rotate(25deg);transform-origin:bottom}
.screen{min-height:0;overflow:hidden;border:1px solid #354238;border-radius:9px;background:linear-gradient(180deg,#0a150c,#071009);box-shadow:inset 0 0 38px rgba(78,188,109,.04),0 0 0 4px #090b09,0 0 0 5px #272d27;display:grid;grid-template-columns:minmax(150px,.72fr) minmax(320px,1.65fr) minmax(170px,.78fr);position:relative}.screen:before{content:"";position:absolute;inset:0;pointer-events:none;opacity:.2;background:repeating-linear-gradient(180deg,transparent 0 3px,rgba(154,228,167,.035) 4px)}.panel{min-width:0;min-height:0;padding:14px;position:relative;z-index:1}.panel+.panel{border-left:1px solid rgba(154,228,167,.09)}.label{color:#5f7c65;font:800 7px/1.2 ui-monospace,monospace;letter-spacing:.15em;text-transform:uppercase}.status-grid{display:grid;gap:8px;margin-top:12px}.status-row{display:flex;justify-content:space-between;gap:8px;border-bottom:1px solid rgba(154,228,167,.08);padding-bottom:7px;font:700 8px/1.2 ui-monospace,monospace}.status-row span{color:#64816a}.status-row b{color:#a6dbaf;text-align:right;overflow:hidden;text-overflow:ellipsis}.status-row b.orange{color:var(--orange)}
.rx-panel{display:grid;grid-template-rows:auto minmax(0,1fr) auto;gap:8px}.rx-head{display:flex;justify-content:space-between;align-items:center;gap:12px}.rx-state{display:flex;align-items:center;gap:7px;color:var(--green);font:850 9px/1 ui-monospace,monospace;letter-spacing:.1em}.dot{width:7px;height:7px;border-radius:50%;background:var(--green);box-shadow:0 0 12px var(--green)}.bars{display:flex;gap:3px;align-items:end;height:17px}.bars i{display:block;width:4px;background:var(--green2)}.bars i:nth-child(1){height:4px}.bars i:nth-child(2){height:7px}.bars i:nth-child(3){height:10px}.bars i:nth-child(4){height:13px}.bars i:nth-child(5){height:17px}.rx-core{min-height:0;display:flex;flex-direction:column;justify-content:center;overflow:hidden}.channel-tag{color:#628269;font:800 7px/1 ui-monospace,monospace;letter-spacing:.16em}.channel{margin:5px 0 2px;color:#c6f4cf;font:950 clamp(28px,5vw,62px)/.86 ui-monospace,monospace;letter-spacing:-.07em;white-space:nowrap}.channel-sub{color:#64836a;font:750 8px/1.25 ui-monospace,monospace;letter-spacing:.09em}.wave{height:clamp(42px,10vh,80px);display:flex;align-items:center;gap:3px;margin-top:10px;border-top:1px solid rgba(154,228,167,.08);border-bottom:1px solid rgba(154,228,167,.08);overflow:hidden}.wave i{display:block;flex:1;max-width:5px;min-width:2px;border-radius:2px;background:linear-gradient(var(--green),#27673a);height:var(--h);animation:pulse 1.6s ease-in-out infinite alternate;animation-delay:var(--d);opacity:.84}.telemetry{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;background:rgba(154,228,167,.08);border:1px solid rgba(154,228,167,.08)}.metric{background:#09110a;padding:7px;min-width:0}.metric span{display:block;color:#58725e;font:800 6px/1 ui-monospace,monospace;letter-spacing:.11em;text-transform:uppercase}.metric b{display:block;margin-top:4px;color:#9ed7aa;font:800 8px/1.15 ui-monospace,monospace;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.feed-head{display:flex;justify-content:space-between;gap:6px;color:#66836b;font:800 7px/1 ui-monospace,monospace;letter-spacing:.1em}.feed{display:grid;gap:7px;margin-top:10px}.event{padding:8px;border-left:2px solid #31563a;background:rgba(154,228,167,.025);min-width:0}.event.live{border-color:var(--orange)}.event b{display:block;color:#5f8b69;font:800 7px/1 ui-monospace,monospace}.event.live b{color:var(--orange)}.event span{display:block;margin-top:4px;color:#8ca992;font:650 8px/1.35 ui-monospace,monospace;overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}.event.live span{color:#b8cdbb}.safety{position:absolute;left:14px;right:14px;bottom:12px;color:#58705d;font:750 6px/1.3 ui-monospace,monospace;letter-spacing:.08em;text-transform:uppercase}
.keys{display:grid;grid-template-columns:repeat(5,1fr);gap:8px}.key{border:1px solid #2a302a;border-radius:7px;background:linear-gradient(#1a1e1a,#111411);text-decoration:none;color:inherit;padding:7px 10px;display:flex;align-items:center;gap:8px;min-width:0;box-shadow:inset 0 1px rgba(255,255,255,.025)}.key:hover{border-color:rgba(243,107,22,.5)}.key b{color:var(--orange);font:800 7px/1 ui-monospace,monospace}.key span{font:850 9px/1 ui-monospace,monospace;letter-spacing:.06em;white-space:nowrap}.key.disabled{opacity:.4}
footer{display:flex;align-items:center;justify-content:space-between;gap:10px;border-top:1px solid var(--line);color:#5d665e;font:750 7px/1 ui-monospace,monospace;text-transform:uppercase;letter-spacing:.09em;min-width:0}.principles{display:flex;gap:8px;color:#747d75;white-space:nowrap}.principles b:first-child{color:var(--orange)}.build{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;text-align:right}.build span{color:#89928a}
@keyframes pulse{from{transform:scaleY(.35);opacity:.42}to{transform:scaleY(1);opacity:.95}}@media(prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
@media(max-width:960px){.screen{grid-template-columns:minmax(130px,.58fr) minmax(300px,1.45fr)}.screen>.panel:last-child{display:none}.nav a:nth-of-type(3),.nav a:nth-of-type(4){display:none}.keys{grid-template-columns:repeat(5,1fr)}}
@media(max-width:680px){.app{padding:0 8px;grid-template-rows:56px minmax(0,1fr) 30px}.brand img{width:38px;height:38px}.brand-copy span,.state .pill:first-child,.nav{display:none}.console{border-radius:13px;padding:8px;grid-template-rows:38px minmax(0,1fr) 46px}.console-head{grid-template-columns:1fr auto}.mode{display:none}.knob{width:28px;height:28px}.knob:after{left:13px;height:7px}.unit img{width:29px;height:29px}.screen{grid-template-columns:1fr}.screen>.panel:first-child,.screen>.panel:last-child{display:none}.panel+.panel{border-left:0}.panel{padding:12px}.channel{font-size:clamp(34px,13vw,58px)}.wave{height:clamp(46px,13vh,76px)}.telemetry{grid-template-columns:1fr 1fr}.keys{gap:5px}.key{padding:6px;justify-content:center}.key b{display:none}.key span{font-size:7px}.principles{gap:5px;font-size:6px}.build{font-size:6px;max-width:42vw}}
@media(max-height:620px){.app{grid-template-rows:48px minmax(0,1fr) 26px}.brand img{width:34px;height:34px}.brand-copy span{display:none}.console{padding:7px;grid-template-rows:34px minmax(0,1fr) 42px}.console-head{padding:0 5px}.knob{width:26px;height:26px}.screen{grid-template-columns:minmax(120px,.6fr) minmax(280px,1.4fr)}.screen>.panel:last-child{display:none}.panel{padding:10px}.status-grid{margin-top:7px;gap:5px}.status-row{padding-bottom:4px}.channel{font-size:clamp(28px,7vh,48px)}.wave{height:38px;margin-top:6px}.metric{padding:5px}.keys{gap:5px}.key{padding:5px 7px}.key span{font-size:7px}}
</style>
</head>
<body>
<div class="app">
<header>
  <a class="brand" href="https://www.terrasatch.com" aria-label="TerraSatch home"><img src="__BRAND_LOGO__" alt="TerraSatch Sassy Sasquatch logo"><span class="brand-copy"><strong>TERRASATCH RADIO CONSOLE</strong><span>Terrain Intelligence · TerraListen</span></span></a>
  <div class="state"><span class="pill">__ENVIRONMENT__</span><span class="pill live" id="header-state">CHECKING</span></div>
  <nav class="nav" aria-label="API resources"><a href="/health/ready">Health</a>__DOCS_NAV__<a href="/openapi.json">OpenAPI</a><a href="/admin">Admin</a></nav>
</header>
<main>
  <section class="console" aria-label="TerraSatch radio console">
    <div class="console-head">
      <div class="unit"><img src="__BRAND_LOGO__" alt=""><div><strong>TERRASATCH · SASSY</strong><small>WASATCH FRONT · UTAH</small></div></div>
      <div class="mode">MODE: <b>RECEIVE + STRUCTURE</b> · TX: DISABLED</div>
      <div class="knobs" aria-hidden="true"><i class="knob"></i><i class="knob"></i></div>
    </div>
    <div class="screen">
      <aside class="panel">
        <div class="label">SYSTEM STATUS</div>
        <div class="status-grid">
          <div class="status-row"><span>API</span><b id="api-state">CHECKING</b></div>
          <div class="status-row"><span>DATABASE</span><b id="db-state">CHECKING</b></div>
          <div class="status-row"><span>REDIS</span><b id="redis-state">CHECKING</b></div>
          <div class="status-row"><span>INGEST</span><b class="orange">EDGE READY</b></div>
          <div class="status-row"><span>ENV</span><b>__ENVIRONMENT__</b></div>
          <div class="status-row"><span>DEPLOY</span><b>__DEPLOYMENT__</b></div>
          <div class="status-row"><span>VERSION</span><b>v__VERSION__</b></div>
          <div class="status-row"><span>REV</span><b id="revision">UNKNOWN</b></div>
        </div>
      </aside>
      <section class="panel rx-panel">
        <div class="rx-head"><div class="rx-state"><i class="dot"></i><span id="rx-state">RX · CHECKING</span></div><div class="bars" aria-label="signal"><i></i><i></i><i></i><i></i><i></i></div></div>
        <div class="rx-core">
          <div class="channel-tag">TERRALISTEN CORE · CHANNEL 01</div>
          <div class="channel">RX READY</div>
          <div class="channel-sub">RADIO → TRANSCRIPT → TERRAENGINE → EVENT</div>
          <div class="wave" aria-hidden="true">
            <i style="--h:18%;--d:-.1s"></i><i style="--h:42%;--d:-.5s"></i><i style="--h:72%;--d:-.9s"></i><i style="--h:31%;--d:-.3s"></i><i style="--h:88%;--d:-1.1s"></i><i style="--h:53%;--d:-.7s"></i><i style="--h:25%;--d:-.2s"></i><i style="--h:68%;--d:-.8s"></i><i style="--h:92%;--d:-1.2s"></i><i style="--h:38%;--d:-.4s"></i><i style="--h:61%;--d:-.6s"></i><i style="--h:22%;--d:-.15s"></i><i style="--h:79%;--d:-1s"></i><i style="--h:47%;--d:-.55s"></i><i style="--h:30%;--d:-.25s"></i><i style="--h:70%;--d:-.85s"></i><i style="--h:96%;--d:-1.25s"></i><i style="--h:44%;--d:-.45s"></i><i style="--h:64%;--d:-.65s"></i><i style="--h:28%;--d:-.05s"></i>
          </div>
        </div>
        <div class="telemetry">
          <div class="metric"><span>API</span><b>api.terrasatch.com</b></div><div class="metric"><span>PIPELINE</span><b>DETERMINISTIC</b></div><div class="metric"><span>REALTIME</span><b>WS / EVENTS</b></div><div class="metric"><span>SAFETY</span><b>RECEIVE ONLY</b></div>
        </div>
      </section>
      <aside class="panel">
        <div class="feed-head"><span>LIVE SYSTEM FEED</span><span>UTC</span></div>
        <div class="feed">
          <div class="event live"><b>NOW</b><span id="feed-health">Checking API, database, and Redis readiness.</span></div>
          <div class="event"><b>INGEST</b><span>Authorized text and edge inputs enter the canonical transmission pipeline.</span></div>
          <div class="event"><b>ENGINE</b><span>TerraEngine structures field context without autonomous radio transmission.</span></div>
        </div>
        <div class="safety">Receive-side intelligence · Human decision support</div>
      </aside>
    </div>
    <div class="keys">
      <a class="key" href="/health/ready"><b>F1</b><span>HEALTH</span></a>__DOCS_KEY__<a class="key" href="/openapi.json"><b>F3</b><span>OPENAPI</span></a><a class="key" href="/api/v1/reference"><b>F4</b><span>REFERENCE</span></a><a class="key" href="/admin"><b>F5</b><span>ADMIN</span></a>
    </div>
  </section>
</main>
<footer><div class="principles"><b>LISTEN</b><b>WATCH</b><b>LEARN</b><b>ADAPT</b></div><div class="build"><span>__DEPLOYMENT__</span> · REV <span id="footer-revision">UNKNOWN</span> · API ONLINE</div></footer>
</div>
<script>
(async()=>{const $=id=>document.getElementById(id);try{const r=await fetch('/health/ready',{cache:'no-store'}),p=await r.json(),deps=Object.fromEntries((p.dependencies||[]).map(d=>[d.name,d.status]));const ok=r.ok&&p.status==='healthy';$('header-state').textContent=ok?'SYSTEMS ONLINE':'DEGRADED';$('rx-state').textContent=ok?'RX · ONLINE':'RX · DEGRADED';$('api-state').textContent=ok?'HEALTHY':'DEGRADED';$('db-state').textContent=(deps.database||'unknown').toUpperCase();$('redis-state').textContent=(deps.redis||'unknown').toUpperCase();$('feed-health').textContent=ok?'API + database + Redis ready. Receive-side backend online.':'Readiness degraded. Inspect health endpoint.';const rev=(p.revision||'unknown').toString();$('revision').textContent=rev;$('footer-revision').textContent=rev}catch(_e){$('header-state').textContent='UNAVAILABLE';$('rx-state').textContent='RX · UNKNOWN';$('api-state').textContent='UNKNOWN';$('db-state').textContent='UNKNOWN';$('redis-state').textContent='UNKNOWN';$('feed-health').textContent='Readiness request failed.'}})();
</script>
</body>
</html>"""

    for marker, value in replacements.items():
        html = html.replace(marker, value)
    return html
