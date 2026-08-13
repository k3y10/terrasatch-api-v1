"""Lightweight branded landing page for the public TerraSatch API host."""

from __future__ import annotations

from html import escape


_BRAND_LOGO_URL = "https://www.terrasatch.com/terralisten-sasquatch.png"
_BRAND_LOGO_FALLBACK_URL = "/assets/terrasatch-logo.svg"


def build_landing_page(
    *,
    environment: str,
    deployment: str,
    version: str,
    docs_enabled: bool,
) -> str:
    """Return a viewport-fixed TerraSatch receive-side radio console."""

    docs_button = (
        '<a class="key" href="/docs"><b>F2</b><span>DOCS</span></a>'
        if docs_enabled
        else '<span class="key disabled"><b>F2</b><span>DOCS OFF</span></span>'
    )
    docs_nav = '<a href="/docs">Docs</a>' if docs_enabled else '<span class="off">Docs Off</span>'

    replacements = {
        "__ENVIRONMENT__": escape(environment.upper()),
        "__DEPLOYMENT__": escape(deployment),
        "__VERSION__": escape(version),
        "__DOCS_BUTTON__": docs_button,
        "__DOCS_NAV__": docs_nav,
        "__BRAND_LOGO__": _BRAND_LOGO_URL,
        "__BRAND_FALLBACK__": _BRAND_LOGO_FALLBACK_URL,
    }

    html = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
  <meta name="theme-color" content="#071521">
  <meta name="description" content="TerraSatch TerraListen receive-side field radio intelligence console.">
  <title>TerraSatch · TerraListen Radio Console</title>
  <style>
    :root{color-scheme:dark;--navy:#071521;--black:#050807;--case:#111714;--case2:#171e1a;--screen:#07140b;--cream:#f0e6d0;--muted:#7d8982;--line:rgba(240,230,208,.12);--orange:#f36b16;--amber:#f4a52c;--green:#8fe39f;--green2:#4ab96a}
    *{box-sizing:border-box}html,body{width:100%;height:100%;margin:0;overflow:hidden}body{font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:radial-gradient(circle at 48% -20%,rgba(243,107,22,.18),transparent 38%),linear-gradient(180deg,var(--navy),var(--black) 72%);color:var(--cream)}body:before{content:"";position:fixed;inset:0;pointer-events:none;opacity:.18;background-image:linear-gradient(rgba(240,230,208,.035) 1px,transparent 1px),linear-gradient(90deg,rgba(240,230,208,.035) 1px,transparent 1px);background-size:28px 28px}.app{height:100dvh;min-height:0;display:grid;grid-template-rows:64px minmax(0,1fr) 34px;overflow:hidden}.mono{font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace}a{color:inherit}
    header{z-index:5;display:flex;align-items:center;justify-content:space-between;gap:18px;padding:0 max(16px,3vw);border-bottom:1px solid var(--line);background:rgba(5,8,7,.76);backdrop-filter:blur(18px)}.brand{display:flex;align-items:center;gap:10px;min-width:0;text-decoration:none}.brand img{width:45px;height:45px;object-fit:contain;filter:drop-shadow(0 0 10px rgba(243,107,22,.18))}.brandtext{display:grid;line-height:1}.brandtext strong{font-size:14px;letter-spacing:.12em}.brandtext small{margin-top:5px;font:700 8px/1 ui-monospace,monospace;letter-spacing:.15em;color:#8c978f;text-transform:uppercase}.topstate{display:flex;align-items:center;gap:8px}.pill{border:1px solid var(--line);border-radius:999px;padding:6px 9px;font:800 8px/1 ui-monospace,monospace;letter-spacing:.1em}.pill.live{color:var(--green);border-color:rgba(143,227,159,.25);background:rgba(143,227,159,.06)}.dot{display:inline-block;width:6px;height:6px;border-radius:50%;margin-right:6px;background:currentColor;box-shadow:0 0 8px currentColor}.nav{display:flex;gap:12px}.nav a,.nav span{font:750 9px/1 ui-monospace,monospace;text-decoration:none;text-transform:uppercase;color:#919b93}.nav a:hover{color:var(--orange)}.off{opacity:.4}
    .workspace{min-height:0;overflow:hidden;padding:14px max(14px,2.1vw);display:grid;grid-template-columns:minmax(150px,.72fr) minmax(380px,2.25fr) minmax(180px,.85fr);gap:12px}.panel,.radio{min-width:0;min-height:0;border:1px solid var(--line);background:rgba(12,16,13,.78);box-shadow:0 18px 50px rgba(0,0,0,.28)}.panel{border-radius:14px;padding:14px;overflow:hidden}.panel-title{display:flex;align-items:center;justify-content:space-between;gap:8px;padding-bottom:9px;border-bottom:1px solid var(--line);font:800 8px/1 ui-monospace,monospace;letter-spacing:.13em;color:#8d978f;text-transform:uppercase}.panel-title b{color:var(--orange)}
    .status-stack{display:grid;gap:7px;margin-top:10px}.status{display:grid;grid-template-columns:auto 1fr;align-items:center;gap:9px;padding:8px;border:1px solid rgba(240,230,208,.07);background:rgba(255,255,255,.014)}.lamp{width:7px;height:7px;border-radius:50%;background:var(--green);box-shadow:0 0 9px rgba(143,227,159,.6)}.status small{display:block;color:#667168;font:700 7px/1.1 ui-monospace,monospace;letter-spacing:.11em}.status strong{display:block;margin-top:3px;color:#a9b7ab;font:750 9px/1.1 ui-monospace,monospace}.identity{margin-top:12px;padding-top:10px;border-top:1px solid var(--line);display:grid;gap:7px}.identity div{display:flex;justify-content:space-between;gap:7px;font:700 7.5px/1.2 ui-monospace,monospace}.identity span{color:#626d65}.identity b{color:#9ca79e;text-align:right;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
    .radio{border-radius:20px;padding:10px;background:linear-gradient(145deg,#1b211c,#0b0f0c 68%);display:grid;grid-template-rows:44px minmax(0,1fr) 50px;position:relative}.radio:before,.radio:after{content:"";position:absolute;top:9px;width:6px;height:6px;border-radius:50%;background:#040504;border:1px solid #333b34}.radio:before{left:10px}.radio:after{right:10px}.radio-head{display:flex;align-items:center;justify-content:space-between;padding:0 10px 5px;gap:10px}.device{display:flex;align-items:center;gap:8px}.device img{width:35px;height:35px;object-fit:contain}.device strong{font-size:10px;letter-spacing:.11em}.device small{display:block;margin-top:4px;color:#737d75;font:700 7px/1 ui-monospace,monospace;letter-spacing:.1em}.knobs{display:flex;gap:8px}.knob{width:32px;height:32px;border-radius:50%;border:1px solid #303730;background:radial-gradient(circle at 39% 34%,#303830 0 15%,#151a16 17% 51%,#060806 53% 61%,#242b25 63%);position:relative}.knob:after{content:"";position:absolute;width:2px;height:8px;left:15px;top:3px;background:var(--orange);transform:rotate(29deg);transform-origin:bottom}
    .screen{min-height:0;overflow:hidden;border:1px solid #344638;border-radius:8px;background:linear-gradient(180deg,#08150c,#061009);box-shadow:inset 0 0 40px rgba(74,185,106,.045),0 0 0 4px #080b08;display:grid;grid-template-columns:minmax(0,1.35fr) minmax(190px,.65fr);position:relative}.screen:after{content:"";position:absolute;inset:0;pointer-events:none;background:repeating-linear-gradient(180deg,transparent 0 3px,rgba(143,227,159,.025) 4px)}.rx-main,.event-side{min-height:0;position:relative;z-index:1}.rx-main{padding:16px;display:grid;grid-template-rows:auto auto minmax(44px,1fr) auto}.rxline{display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid rgba(143,227,159,.12);padding-bottom:8px;color:var(--green);font:800 8px/1 ui-monospace,monospace;letter-spacing:.12em}.signal{display:flex;align-items:end;gap:2px;height:14px}.signal i{width:4px;background:var(--green2)}.signal i:nth-child(1){height:4px}.signal i:nth-child(2){height:7px}.signal i:nth-child(3){height:10px}.signal i:nth-child(4){height:13px}.channel{padding:12px 0 8px}.channel small{color:#66846d;font:800 7px/1 ui-monospace,monospace;letter-spacing:.16em}.channel strong{display:block;margin-top:4px;color:#c6ffd0;font:900 clamp(27px,4vw,58px)/.9 ui-monospace,monospace;letter-spacing:-.06em}.channel em{display:block;margin-top:6px;color:#66836c;font:700 8px/1.2 ui-monospace,monospace;font-style:normal;letter-spacing:.08em}.wave{min-height:38px;display:flex;align-items:center;gap:3px;overflow:hidden;border-top:1px solid rgba(143,227,159,.08);border-bottom:1px solid rgba(143,227,159,.08)}.wave i{width:3px;min-width:3px;height:var(--h);max-height:70%;border-radius:2px;background:linear-gradient(var(--green),#276d3a);animation:wave 1.4s ease-in-out infinite alternate;animation-delay:var(--d)}.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;margin-top:8px;background:rgba(143,227,159,.08)}.metric{padding:8px;background:#071009}.metric span{display:block;color:#58705e;font:700 6.5px/1 ui-monospace,monospace;letter-spacing:.11em}.metric b{display:block;margin-top:4px;color:#9eddaa;font:750 8px/1.15 ui-monospace,monospace;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.event-side{border-left:1px solid rgba(143,227,159,.1);padding:14px;display:grid;grid-template-rows:auto 1fr auto}.feed-title{font:800 7px/1 ui-monospace,monospace;letter-spacing:.13em;color:#67836d}.feed{display:grid;align-content:center;gap:7px}.feedrow{border-left:2px solid #31533a;padding:7px;background:rgba(143,227,159,.025)}.feedrow.live{border-color:var(--orange)}.feedrow b{display:block;color:#6b9774;font:800 7px/1.1 ui-monospace,monospace}.feedrow.live b{color:var(--orange)}.feedrow span{display:block;margin-top:4px;color:#91aa96;font:650 8px/1.3 ui-monospace,monospace}.receive-note{color:#58705e;font:700 6.5px/1.3 ui-monospace,monospace;letter-spacing:.08em}
    .keys{display:grid;grid-template-columns:repeat(5,1fr);gap:6px;padding-top:8px}.key{min-width:0;border:1px solid #2b322c;border-radius:7px;background:linear-gradient(#1b211c,#101411);display:flex;align-items:center;justify-content:center;gap:6px;text-decoration:none;font:800 8px/1 ui-monospace,monospace;letter-spacing:.06em}.key:hover{border-color:rgba(243,107,22,.55)}.key b{color:var(--orange)}.key span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.key.disabled{opacity:.35}
    .action-stack{display:grid;gap:7px;margin-top:10px}.action{border:1px solid rgba(240,230,208,.08);padding:9px;text-decoration:none;background:rgba(255,255,255,.014)}.action b{display:block;font:800 8px/1 ui-monospace,monospace;color:#aeb8b0}.action span{display:block;margin-top:4px;font:650 7px/1.25 ui-monospace,monospace;color:#616b64}.action.primary{border-color:rgba(243,107,22,.28);background:rgba(243,107,22,.045)}.action.primary b{color:var(--orange)}.principles{display:grid;grid-template-columns:1fr 1fr;gap:5px;margin-top:10px}.principles b{padding:7px 5px;text-align:center;border:1px solid var(--line);font:800 7px/1 ui-monospace,monospace;letter-spacing:.08em}.principles b:first-child{color:var(--orange)}
    footer{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:0 max(16px,3vw);border-top:1px solid var(--line);background:rgba(5,8,7,.78);font:700 7px/1 ui-monospace,monospace;letter-spacing:.11em;color:#59645c;text-transform:uppercase}.footer-principles{color:#808b82}.footer-principles b{color:var(--orange)}
    @keyframes wave{from{transform:scaleY(.35);opacity:.45}to{transform:scaleY(1);opacity:.95}}
    @media(max-width:980px){.workspace{grid-template-columns:minmax(135px,.65fr) minmax(0,2.35fr)}.right{display:none}.screen{grid-template-columns:1fr}.event-side{display:none}.nav{display:none}.channel strong{font-size:clamp(30px,7vw,54px)}}
    @media(max-width:650px){.app{grid-template-rows:56px minmax(0,1fr) 28px}.workspace{padding:8px;grid-template-columns:1fr}.left{display:none}.brand img{width:39px;height:39px}.brandtext strong{font-size:12px}.brandtext small{font-size:6.5px}.pill:not(.live){display:none}.radio{border-radius:14px;padding:7px;grid-template-rows:38px minmax(0,1fr) 43px}.radio-head{padding:0 7px 3px}.device img{width:30px;height:30px}.knob{width:27px;height:27px}.knob:after{left:12px}.screen{min-height:0}.rx-main{padding:11px}.metrics{grid-template-columns:1fr 1fr}.metric:nth-child(n+3){display:none}.keys{gap:4px;padding-top:6px}.key{font-size:6.5px}.key b{display:none}footer{font-size:5.8px}.footer-principles{display:none}}
    @media(max-height:620px){.app{grid-template-rows:52px minmax(0,1fr) 24px}.workspace{padding-top:7px;padding-bottom:7px}.panel{padding:9px}.identity{display:none}.status-stack{gap:4px}.status{padding:5px}.radio{grid-template-rows:34px minmax(0,1fr) 39px}.radio-head{padding-bottom:2px}.channel{padding:7px 0 5px}.channel strong{font-size:clamp(24px,6vh,42px)}.metrics{margin-top:5px}.metric{padding:5px}.feedrow:nth-child(n+3){display:none}.keys{padding-top:5px}}
    @media(prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
  </style>
</head>
<body>
  <div class="app">
    <header>
      <a class="brand" href="https://www.terrasatch.com" aria-label="TerraSatch home">
        <img src="__BRAND_LOGO__" onerror="this.onerror=null;this.src='__BRAND_FALLBACK__'" alt="TerraSatch Sasquatch">
        <span class="brandtext"><strong>TERRASATCH</strong><small>TerraListen · Radio Intelligence</small></span>
      </a>
      <div class="topstate"><span class="pill">__ENVIRONMENT__</span><span class="pill live"><i class="dot"></i><span id="header-state">CHECKING</span></span></div>
      <nav class="nav" aria-label="API resources"><a href="/health/ready">Health</a>__DOCS_NAV__<a href="/openapi.json">OpenAPI</a><a href="/admin">Admin</a></nav>
    </header>

    <main class="workspace">
      <aside class="panel left">
        <div class="panel-title"><span>System / RF</span><b>RX</b></div>
        <div class="status-stack">
          <div class="status"><i class="lamp"></i><div><small>API</small><strong id="api-state">CHECKING</strong></div></div>
          <div class="status"><i class="lamp"></i><div><small>DATABASE</small><strong id="db-state">CHECKING</strong></div></div>
          <div class="status"><i class="lamp"></i><div><small>REDIS</small><strong id="redis-state">CHECKING</strong></div></div>
          <div class="status"><i class="lamp"></i><div><small>INGEST</small><strong>READY</strong></div></div>
        </div>
        <div class="identity">
          <div><span>DEPLOY</span><b>__DEPLOYMENT__</b></div><div><span>VERSION</span><b>v__VERSION__</b></div><div><span>REVISION</span><b id="revision">—</b></div><div><span>MODE</span><b>RECEIVE ONLY</b></div>
        </div>
      </aside>

      <section class="radio" aria-label="TerraSatch radio console">
        <div class="radio-head">
          <div class="device"><img src="__BRAND_LOGO__" onerror="this.onerror=null;this.src='__BRAND_FALLBACK__'" alt=""><div><strong>TERRALISTEN</strong><small>FIELD INTELLIGENCE RECEIVER</small></div></div>
          <div class="knobs" aria-hidden="true"><i class="knob"></i><i class="knob"></i></div>
        </div>
        <div class="screen">
          <div class="rx-main">
            <div class="rxline"><span><i class="dot"></i><span id="rx-state">RX · CHECKING</span></span><span class="signal"><i></i><i></i><i></i><i></i></span></div>
            <div class="channel"><small>ACTIVE SERVICE</small><strong>API · RX</strong><em>RADIO → TRANSCRIPT → TERRAENGINE → EVENT</em></div>
            <div class="wave" aria-hidden="true">__WAVE__</div>
            <div class="metrics"><div class="metric"><span>MODE</span><b>RECEIVE + STRUCTURE</b></div><div class="metric"><span>TX</span><b>DISABLED</b></div><div class="metric"><span>SOCKET</span><b>/ws/v1/events</b></div><div class="metric"><span>INGEST</span><b>/api/v1/transmissions</b></div></div>
          </div>
          <aside class="event-side"><div class="feed-title">LIVE SYSTEM FEED</div><div class="feed"><div class="feedrow live"><b>CORE</b><span id="feed-health">Checking API dependencies…</span></div><div class="feedrow"><b>PIPELINE</b><span>Transmission ingestion + structured events ready.</span></div><div class="feedrow"><b>EDGE</b><span>Receive-side hardware bridge is the next field input.</span></div></div><div class="receive-note">DECISION SUPPORT · AUTHORIZED INPUTS · NO AUTONOMOUS RADIO TRANSMISSION</div></aside>
        </div>
        <div class="keys"><a class="key" href="/health/ready"><b>F1</b><span>HEALTH</span></a>__DOCS_BUTTON__<a class="key" href="/openapi.json"><b>F3</b><span>OPENAPI</span></a><a class="key" href="/api/v1/reference"><b>F4</b><span>REFERENCE</span></a><a class="key" href="/admin"><b>F5</b><span>ADMIN</span></a></div>
      </section>

      <aside class="panel right">
        <div class="panel-title"><span>Gateways</span><b>LIVE</b></div>
        <div class="action-stack"><a class="action primary" href="/api/v1/reference"><b>API REFERENCE</b><span>Routes, scopes and errors</span></a><a class="action" href="/openapi.json"><b>OPENAPI</b><span>Machine-readable contract</span></a><a class="action" href="/admin"><b>ADMIN</b><span>Organizations and access</span></a><a class="action" href="/health/ready"><b>READINESS</b><span>Database + Redis state</span></a></div>
        <div class="principles"><b>LISTEN</b><b>WATCH</b><b>LEARN</b><b>ADAPT</b></div>
      </aside>
    </main>

    <footer><span>TerraSatch · Terrain Intelligence · Wasatch Front, Utah</span><span class="footer-principles"><b>LISTEN</b> · WATCH · LEARN · ADAPT</span><span>api.terrasatch.com</span></footer>
  </div>
  <script>
    (async()=>{const q=id=>document.getElementById(id);try{const r=await fetch('/health/ready',{cache:'no-store'}),p=await r.json(),healthy=r.ok&&p.status==='healthy';q('header-state').textContent=healthy?'SYSTEMS ONLINE':'DEGRADED';q('rx-state').textContent=healthy?'RX · ONLINE':'RX · DEGRADED';q('api-state').textContent=healthy?'HEALTHY':'DEGRADED';q('revision').textContent=p.revision||'—';const deps=Object.fromEntries((p.dependencies||[]).map(d=>[d.name,d.status]));q('db-state').textContent=(deps.database||'unknown').toUpperCase();q('redis-state').textContent=(deps.redis||'unknown').toUpperCase();q('feed-health').textContent=healthy?'API + database + Redis ready.':'Readiness degraded · inspect health.'}catch(_){q('header-state').textContent='UNAVAILABLE';q('rx-state').textContent='RX · UNKNOWN';q('api-state').textContent='UNKNOWN';q('db-state').textContent='UNKNOWN';q('redis-state').textContent='UNKNOWN';q('feed-health').textContent='Readiness request failed.'}})();
  </script>
</body>
</html>"""

    wave = "".join(
        f'<i style="--h:{height}%;--d:-{index * 0.07:.2f}s"></i>'
        for index, height in enumerate(
            (28,52,36,68,44,74,31,59,82,38,71,48,88,41,64,33,78,46,57,84,39,69,50,76,34,61,45,87,40,72,53,66,32,81,43,58,75,37,63,49,85,35,70,47,79,42,60,73)
        )
    )
    replacements["__WAVE__"] = wave
    for marker, value in replacements.items():
        html = html.replace(marker, value)
    return html
