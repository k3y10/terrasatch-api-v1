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
    """Return a dependency-light TerraSatch radio-console portal without exposing secrets."""

    docs_softkey = (
        '<a class="softkey" href="/docs"><span>F2</span><strong>SWAGGER</strong><small>Interactive API</small></a>'
        if docs_enabled
        else '<div class="softkey disabled"><span>F2</span><strong>SWAGGER</strong><small>Disabled</small></div>'
    )
    docs_nav = (
        '<a href="/docs">Swagger</a>'
        if docs_enabled
        else '<span class="disabled-link">Swagger Off</span>'
    )

    replacements = {
        "__ENVIRONMENT__": escape(environment),
        "__DEPLOYMENT__": escape(deployment),
        "__VERSION__": escape(version),
        "__DOCS_SOFTKEY__": docs_softkey,
        "__DOCS_NAV__": docs_nav,
        "__BRAND_LOGO__": _BRAND_LOGO_URL,
    }

    html = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="theme-color" content="#090b09">
  <meta name="description" content="TerraSatch field intelligence API radio console for authorized partner applications and remote operations.">
  <title>TerraSatch API · Radio Console</title>
  <style>
    :root {
      color-scheme: dark;
      --bg:#070907; --case:#121512; --case2:#191d19; --screen:#0b120d; --screen2:#101a12;
      --text:#f5efe1; --cream:#eee3ca; --muted:#8d968d; --faint:#596159;
      --line:rgba(238,227,202,.12); --line2:rgba(238,227,202,.22);
      --orange:#f36b16; --amber:#f4a52c; --green:#94e3a3; --green2:#4fbf70;
    }
    *{box-sizing:border-box} html{background:var(--bg)} body{margin:0;min-height:100vh;color:var(--text);font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:radial-gradient(circle at 50% 0,rgba(243,107,22,.12),transparent 34rem),linear-gradient(180deg,#0b0d0b,#070907 70%);overflow-x:hidden}
    body:before{content:"";position:fixed;inset:0;pointer-events:none;opacity:.25;background-image:linear-gradient(rgba(238,227,202,.025) 1px,transparent 1px),linear-gradient(90deg,rgba(238,227,202,.025) 1px,transparent 1px);background-size:32px 32px;mask-image:linear-gradient(#000,transparent 85%)}
    a{color:inherit}.shell{width:min(1280px,calc(100% - 30px));margin:auto;position:relative;z-index:1}.mono{font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace}.micro{font:700 9px/1.2 ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;letter-spacing:.17em;text-transform:uppercase}
    header{min-height:84px;display:flex;align-items:center;justify-content:space-between;gap:18px;border-bottom:1px solid var(--line)}.brand{display:flex;align-items:center;gap:12px;text-decoration:none}.brand img{width:50px;height:50px}.brand-copy{display:grid;gap:2px}.brand-copy strong{font-size:15px;letter-spacing:.09em}.brand-copy span{color:var(--muted);font-size:9px;letter-spacing:.16em;text-transform:uppercase}.topnav{display:flex;gap:16px;flex-wrap:wrap;justify-content:flex-end}.topnav a,.topnav span{font:700 10px/1 ui-monospace,monospace;text-decoration:none;color:#aeb6ad;text-transform:uppercase;letter-spacing:.09em}.topnav a:hover{color:var(--orange)}.disabled-link{opacity:.4}
    .hero{padding:42px 0 28px}.eyebrow{display:flex;align-items:center;gap:9px;color:var(--orange);margin-bottom:14px}.eyebrow:before{content:"";width:24px;height:1px;background:var(--orange)}h1{margin:0;font-size:clamp(38px,6.8vw,88px);line-height:.9;letter-spacing:-.045em;text-transform:uppercase;font-weight:900}h1 .accent{color:var(--orange)}.sub{max-width:760px;margin:18px 0 0;color:#a8afa7;line-height:1.65;font-size:15px}
    .radio{margin:34px 0 24px;border:1px solid #272d27;border-radius:24px;background:linear-gradient(145deg,#1a1e1a,#0f120f 65%);box-shadow:0 38px 100px rgba(0,0,0,.48),inset 0 1px rgba(255,255,255,.035);padding:18px;position:relative}.radio:before,.radio:after{content:"";position:absolute;top:12px;width:7px;height:7px;border-radius:50%;background:#060706;border:1px solid #343a34;box-shadow:inset 0 1px 2px #000}.radio:before{left:13px}.radio:after{right:13px}.radio-top{display:grid;grid-template-columns:150px 1fr 180px;gap:14px;align-items:center;padding:12px 14px 17px}.radio-id{display:flex;align-items:center;gap:10px}.radio-id img{width:42px;height:42px}.radio-id strong{display:block;font-size:12px;letter-spacing:.08em}.radio-id small{color:var(--muted);font:700 8px/1.4 ui-monospace,monospace;letter-spacing:.12em}.statusline{text-align:center;color:#6d756d;font:700 9px/1.4 ui-monospace,monospace;letter-spacing:.12em;text-transform:uppercase}.statusline b{color:var(--green)}.knobs{display:flex;justify-content:flex-end;gap:12px}.knob{width:48px;height:48px;border-radius:50%;background:radial-gradient(circle at 40% 34%,#2d332d 0 17%,#151915 19% 48%,#070907 50% 60%,#252b25 62% 100%);border:1px solid #303630;box-shadow:0 7px 14px rgba(0,0,0,.45);position:relative}.knob:after{content:"";position:absolute;width:2px;height:12px;background:var(--orange);left:23px;top:5px;transform:rotate(28deg);transform-origin:bottom}
    .screen{border:1px solid #334036;background:linear-gradient(180deg,#0b130d,#081009);box-shadow:inset 0 0 35px rgba(79,191,112,.045),0 0 0 5px #0a0c0a,0 0 0 6px #282d28;border-radius:10px;padding:20px;min-height:400px;display:grid;grid-template-columns:minmax(0,1.2fr) minmax(300px,.8fr);gap:22px;position:relative;overflow:hidden}.screen:before{content:"";position:absolute;inset:0;pointer-events:none;opacity:.18;background:repeating-linear-gradient(180deg,transparent 0 3px,rgba(148,227,163,.04) 4px)}.screen-main,.screen-side{position:relative;z-index:1}.rx-line{display:flex;align-items:center;justify-content:space-between;gap:15px;border-bottom:1px solid rgba(148,227,163,.12);padding-bottom:13px}.rx{display:flex;align-items:center;gap:8px;color:var(--green)}.rx-dot{width:8px;height:8px;border-radius:50%;background:var(--green);box-shadow:0 0 14px rgba(148,227,163,.75)}.bars{display:flex;align-items:end;gap:3px;height:20px}.bars i{display:block;width:5px;background:var(--green2);opacity:.9}.bars i:nth-child(1){height:5px}.bars i:nth-child(2){height:8px}.bars i:nth-child(3){height:11px}.bars i:nth-child(4){height:14px}.bars i:nth-child(5){height:18px}.channel{padding:22px 0 12px}.channel small{color:#71917a;font:700 9px/1 ui-monospace,monospace;letter-spacing:.15em}.channel strong{display:block;margin-top:7px;color:#c9ffd2;font:900 clamp(31px,5vw,62px)/.95 ui-monospace,monospace;letter-spacing:-.06em}.channel em{display:block;margin-top:8px;color:#6d8d73;font:700 10px/1.3 ui-monospace,monospace;font-style:normal;letter-spacing:.09em}.wave{height:86px;display:flex;align-items:center;gap:4px;border-top:1px solid rgba(148,227,163,.1);border-bottom:1px solid rgba(148,227,163,.1);overflow:hidden}.wave i{width:4px;min-width:4px;border-radius:2px;background:linear-gradient(var(--green),#2d7e42);height:var(--h);animation:pulsewave 1.7s ease-in-out infinite alternate;animation-delay:var(--d);opacity:.82}.screen-copy{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;margin-top:14px;background:rgba(148,227,163,.1);border:1px solid rgba(148,227,163,.1)}.screen-metric{padding:12px;background:#0a110b}.screen-metric small{display:block;color:#5f7964;font:700 8px/1.2 ui-monospace,monospace;letter-spacing:.12em;text-transform:uppercase}.screen-metric strong{display:block;margin-top:5px;color:#aee9b8;font:700 10px/1.3 ui-monospace,monospace;overflow-wrap:anywhere}.event-head{display:flex;justify-content:space-between;color:#75947b;padding-bottom:10px;border-bottom:1px solid rgba(148,227,163,.12)}.feed{display:grid;gap:8px;margin-top:11px}.feed-row{display:grid;grid-template-columns:48px 1fr;gap:9px;padding:9px;border-left:2px solid #31543a;background:rgba(148,227,163,.025)}.feed-row b{color:#5f8a68;font:700 8px/1.3 ui-monospace,monospace}.feed-row span{color:#92af97;font:600 9px/1.45 ui-monospace,monospace}.feed-row.live{border-color:var(--orange)}.feed-row.live b{color:var(--orange)}.feed-row.live span{color:#c7d9c9}.screen-footer{margin-top:15px;color:#63806a;font:700 8px/1.4 ui-monospace,monospace;letter-spacing:.1em}
    .softkeys{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-top:18px}.softkey{min-height:76px;text-decoration:none;border:1px solid #2b302b;background:linear-gradient(#1a1e1a,#111411);border-radius:9px;padding:11px 12px;box-shadow:inset 0 1px rgba(255,255,255,.035),0 4px 9px rgba(0,0,0,.25);transition:.16s ease}.softkey:hover{transform:translateY(-2px);border-color:rgba(243,107,22,.55)}.softkey span{display:block;color:var(--orange);font:700 8px/1 ui-monospace,monospace}.softkey strong{display:block;margin-top:8px;font:850 12px/1.1 ui-monospace,monospace;letter-spacing:.06em}.softkey small{display:block;margin-top:4px;color:#686f68;font-size:9px}.softkey.disabled{opacity:.42}
    .lower{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin:24px 0 0}.panel{border:1px solid var(--line);background:rgba(255,255,255,.012);padding:20px}.panel h2{margin:6px 0 14px;font-size:20px}.panel p{margin:0;color:var(--muted);font-size:12px;line-height:1.65}.route-list{display:grid;gap:7px;margin-top:16px}.route{display:flex;justify-content:space-between;gap:15px;border-top:1px solid var(--line);padding-top:7px;font:650 9px/1.4 ui-monospace,monospace}.route code{color:#b9c0b8}.route span{color:#697068}.principles{display:flex;gap:8px;flex-wrap:wrap;margin-top:16px}.principles b{padding:7px 8px;border:1px solid var(--line);font:750 8px/1 ui-monospace,monospace;letter-spacing:.1em}.principles b:first-child{color:var(--orange);border-color:rgba(243,107,22,.35)}
    .terrain{height:76px;margin-top:10px;opacity:.7}.terrain svg{width:100%;height:100%}footer{min-height:86px;border-top:1px solid var(--line);display:flex;justify-content:space-between;align-items:center;gap:18px;color:#5d645d;font:700 9px/1.4 ui-monospace,monospace;letter-spacing:.09em;text-transform:uppercase}
    @keyframes pulsewave{from{transform:scaleY(.35);opacity:.45}to{transform:scaleY(1);opacity:.95}}
    @media(max-width:900px){.radio-top{grid-template-columns:1fr auto}.statusline{display:none}.screen{grid-template-columns:1fr}.softkeys{grid-template-columns:repeat(3,1fr)}.lower{grid-template-columns:1fr}}@media(max-width:600px){.shell{width:min(100% - 18px,1280px)}header{align-items:flex-start;flex-direction:column;padding:14px 0}.topnav{justify-content:flex-start}.hero{padding-top:34px}.radio{border-radius:15px;padding:10px}.radio-top{padding:10px 6px}.knobs{display:none}.screen{padding:13px;min-height:0}.screen-copy{grid-template-columns:1fr 1fr}.softkeys{grid-template-columns:1fr 1fr}.softkey:last-child{grid-column:1/-1}footer{align-items:flex-start;flex-direction:column;padding:22px 0}}
    @media(prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
  </style>
</head>
<body>
  <main class="shell">
    <header>
      <a class="brand" href="https://www.terrasatch.com" aria-label="TerraSatch home"><img src="__BRAND_LOGO__" alt="TerraSatch logo"><span class="brand-copy"><strong>TERRASATCH</strong><span>Terrain Intelligence · Radio API</span></span></a>
      <nav class="topnav" aria-label="API resources"><a href="/health/ready">Health</a>__DOCS_NAV__<a href="/openapi.json">OpenAPI</a><a href="/api/v1/reference">Reference</a><a href="/admin">Admin</a></nav>
    </header>

    <section class="hero">
      <div class="eyebrow micro">Wasatch Front · Utah · TerraListen Core</div>
      <h1>Field Radio.<br><span class="accent">Structured Intelligence.</span></h1>
      <p class="sub">The live TerraSatch backend presented like the tool it is becoming: a shared receive-side radio intelligence console for authorized field traffic, structured events, partner applications, and operational decision support.</p>

      <div class="radio" aria-label="TerraSatch radio console">
        <div class="radio-top">
          <div class="radio-id"><img src="__BRAND_LOGO__" alt=""><div><strong>TERRASATCH</strong><small>RX INTELLIGENCE</small></div></div>
          <div class="statusline">SECURE LINK · <b id="header-state">QUERYING</b> · HTTPS/WSS</div>
          <div class="knobs" aria-hidden="true"><i class="knob"></i><i class="knob"></i></div>
        </div>

        <div class="screen">
          <section class="screen-main">
            <div class="rx-line"><div class="rx micro"><i class="rx-dot"></i><span id="rx-state">RX · CHECKING</span></div><div class="bars" aria-label="Signal strength"><i></i><i></i><i></i><i></i><i></i></div></div>
            <div class="channel"><small>CH 01 · TERRASATCH CORE</small><strong>TERRALISTEN</strong><em>MODE: RECEIVE + STRUCTURE · TX: DISABLED</em></div>
            <div class="wave" aria-label="Animated receive waveform">
              <i style="--h:18%;--d:-.2s"></i><i style="--h:34%;--d:-.7s"></i><i style="--h:58%;--d:-1.2s"></i><i style="--h:82%;--d:-.4s"></i><i style="--h:44%;--d:-1.4s"></i><i style="--h:68%;--d:-.9s"></i><i style="--h:28%;--d:-.1s"></i><i style="--h:74%;--d:-1.6s"></i><i style="--h:92%;--d:-.6s"></i><i style="--h:48%;--d:-1.1s"></i><i style="--h:22%;--d:-.3s"></i><i style="--h:64%;--d:-1.3s"></i><i style="--h:87%;--d:-.8s"></i><i style="--h:35%;--d:-.5s"></i><i style="--h:70%;--d:-1.7s"></i><i style="--h:26%;--d:-.2s"></i><i style="--h:51%;--d:-1s"></i><i style="--h:78%;--d:-.6s"></i><i style="--h:39%;--d:-1.5s"></i><i style="--h:63%;--d:-.4s"></i><i style="--h:19%;--d:-1.1s"></i><i style="--h:83%;--d:-.7s"></i><i style="--h:54%;--d:-1.3s"></i><i style="--h:31%;--d:-.3s"></i><i style="--h:72%;--d:-.9s"></i><i style="--h:46%;--d:-1.6s"></i><i style="--h:90%;--d:-.5s"></i><i style="--h:37%;--d:-1.2s"></i><i style="--h:61%;--d:-.8s"></i><i style="--h:25%;--d:-1.4s"></i>
            </div>
            <div class="screen-copy"><div class="screen-metric"><small>Environment</small><strong>__ENVIRONMENT__</strong></div><div class="screen-metric"><small>Deployment</small><strong>__DEPLOYMENT__</strong></div><div class="screen-metric"><small>Version</small><strong>__VERSION__</strong></div><div class="screen-metric"><small>Readiness</small><strong id="ready-value">QUERYING</strong></div></div>
          </section>

          <aside class="screen-side">
            <div class="event-head micro"><span>LIVE SYSTEM FEED</span><span>UTC / RX</span></div>
            <div class="feed">
              <div class="feed-row live"><b>CORE</b><span id="feed-health">Polling /health/ready…</span></div>
              <div class="feed-row"><b>AUTH</b><span>Tenant-scoped bearer API keys ready</span></div>
              <div class="feed-row"><b>RADIO</b><span>Agents · channels · callsigns · transmissions</span></div>
              <div class="feed-row"><b>ENGINE</b><span>Source-linked transcripts + structured events</span></div>
              <div class="feed-row"><b>LINK</b><span>REST + realtime WSS event delivery</span></div>
            </div>
            <div class="screen-footer">40.7608° N · 111.8910° W<br>WASATCH FRONT · UTAH<br>LISTEN · WATCH · LEARN · ADAPT</div>
          </aside>
        </div>

        <div class="softkeys" aria-label="Radio soft keys">
          <a class="softkey" href="/health/ready"><span>F1</span><strong>HEALTH</strong><small>Readiness check</small></a>
          __DOCS_SOFTKEY__
          <a class="softkey" href="/openapi.json"><span>F3</span><strong>OPENAPI</strong><small>Machine contract</small></a>
          <a class="softkey" href="/api/v1/reference"><span>F4</span><strong>REFERENCE</strong><small>Route catalog</small></a>
          <a class="softkey" href="/admin"><span>F5</span><strong>ADMIN</strong><small>Control plane</small></a>
        </div>
      </div>

      <div class="lower">
        <section class="panel"><span class="micro" style="color:var(--orange)">RX PIPELINE</span><h2>Radio → Intelligence → Applications</h2><p>Authorized field traffic is preserved as source transmissions and transcripts before TerraEngine produces structured operational events for downstream demos and partner tools.</p><div class="route-list"><div class="route"><code>POST /api/v1/transmissions</code><span>INGEST</span></div><div class="route"><code>GET /api/v1/transcripts</code><span>SOURCE</span></div><div class="route"><code>GET /api/v1/events</code><span>INTEL</span></div><div class="route"><code>WSS /ws/v1/events</code><span>LIVE</span></div></div></section>
        <section class="panel"><span class="micro" style="color:var(--orange)">FIELD OPERATIONS</span><h2>One Core. Focused Channels.</h2><p>Organizations and sites isolate partner contexts while the same backend can support avalanche, road, park, patrol, wildfire, SAR, utility, and other remote-field workflows.</p><div class="principles"><b>LISTEN</b><b>WATCH</b><b>LEARN</b><b>ADAPT</b></div></section>
      </div>

      <div class="terrain" aria-hidden="true"><svg viewBox="0 0 1280 80" preserveAspectRatio="none"><defs><linearGradient id="ridge" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#f36b16" stop-opacity="0"/><stop offset=".25" stop-color="#f36b16"/><stop offset=".55" stop-color="#f4a52c"/><stop offset="1" stop-color="#f36b16" stop-opacity="0"/></linearGradient></defs><path d="M0 68 120 64 190 48 245 62 318 35 380 61 454 24 526 63 600 41 670 61 746 30 814 60 887 42 955 61 1030 32 1110 57 1180 46 1280 68" fill="none" stroke="url(#ridge)" stroke-width="2"/><g fill="#eee3ca" opacity=".14"><path d="M125 70h24l-12-16h6l-14-20-14 20h6l-12 16h16Z"/><path d="M1090 70h24l-12-16h6l-14-20-14 20h6l-12 16h16Z"/></g></svg></div>
    </section>

    <footer><span>TerraSatch · Terrain Intelligence</span><span>Receive-only decision support · No autonomous radio transmission</span><span>api.terrasatch.com</span></footer>
  </main>
  <script>
    (async()=>{const header=document.getElementById('header-state'),rx=document.getElementById('rx-state'),ready=document.getElementById('ready-value'),feed=document.getElementById('feed-health');try{const r=await fetch('/health/ready',{cache:'no-store'}),p=await r.json();if(r.ok&&p.status==='healthy'){header.textContent='SYSTEMS ONLINE';rx.textContent='RX · ONLINE';ready.textContent='HEALTHY';feed.textContent='API + database + Redis ready'}else{header.textContent='DEGRADED';rx.textContent='RX · DEGRADED';ready.textContent='DEGRADED';feed.textContent='Readiness degraded · inspect health'}}catch(_e){header.textContent='UNAVAILABLE';rx.textContent='RX · UNKNOWN';ready.textContent='UNKNOWN';feed.textContent='Readiness request failed'}})();
  </script>
</body>
</html>"""

    for marker, value in replacements.items():
        html = html.replace(marker, value)
    return html
