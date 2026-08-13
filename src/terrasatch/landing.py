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
    """Return a dependency-light TerraSatch systems portal without exposing secrets."""

    docs_link = (
        '<a class="nav-link" href="/docs">Swagger</a>'
        if docs_enabled
        else (
            '<span class="nav-link disabled" '
            'title="Swagger is disabled in this environment">Swagger Off</span>'
        )
    )
    docs_card = (
        '<a class="gateway" href="/docs"><span class="gateway-index">02</span>'
        '<strong>Swagger</strong><span>Interactive API explorer</span><b>OPEN ↗</b></a>'
        if docs_enabled
        else (
            '<div class="gateway disabled-card"><span class="gateway-index">02</span>'
            '<strong>Swagger</strong><span>Disabled in this environment</span><b>OFFLINE</b></div>'
        )
    )

    replacements = {
        "__ENVIRONMENT__": escape(environment),
        "__DEPLOYMENT__": escape(deployment),
        "__VERSION__": escape(version),
        "__DOCS_LINK__": docs_link,
        "__DOCS_CARD__": docs_card,
        "__BRAND_LOGO__": _BRAND_LOGO_URL,
    }

    html = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="theme-color" content="#090a09">
  <meta name="description" content="TerraSatch field intelligence API for authorized partner applications and remote operations.">
  <title>TerraSatch API · Field Intelligence</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #080908;
      --panel: #101210;
      --panel-2: #151714;
      --cream: #f4eddb;
      --text: #f6f4ed;
      --muted: #93988f;
      --faint: #5f665f;
      --line: rgba(244,237,219,.12);
      --line-strong: rgba(244,237,219,.22);
      --orange: #f36b16;
      --orange-2: #ff9b25;
      --gold: #f2b52c;
      --green: #8ddd9d;
    }
    * { box-sizing: border-box; }
    html { background: var(--bg); }
    body {
      margin: 0;
      min-height: 100vh;
      color: var(--text);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background:
        radial-gradient(circle at 82% 8%, rgba(243,107,22,.14), transparent 28rem),
        radial-gradient(circle at 12% 35%, rgba(242,181,44,.055), transparent 30rem),
        linear-gradient(180deg, #0c0d0c 0%, #080908 58%, #060706 100%);
      overflow-x: hidden;
    }
    body::before {
      content: "";
      position: fixed;
      inset: 0;
      pointer-events: none;
      opacity: .35;
      background-image:
        linear-gradient(rgba(244,237,219,.025) 1px, transparent 1px),
        linear-gradient(90deg, rgba(244,237,219,.025) 1px, transparent 1px);
      background-size: 42px 42px;
      mask-image: linear-gradient(to bottom, #000 0%, transparent 78%);
    }
    a { color: inherit; }
    .shell { width: min(1280px, calc(100% - 34px)); margin: 0 auto; position: relative; z-index: 1; }
    .micro {
      font: 700 10px/1.2 ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      letter-spacing: .19em;
      text-transform: uppercase;
    }
    header {
      min-height: 94px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 20px;
      border-bottom: 1px solid var(--line);
    }
    .brand-lockup { display: flex; align-items: center; gap: 13px; text-decoration: none; min-width: 0; }
    .brand-logo {
      width: 58px;
      height: 58px;
      object-fit: contain;
      filter: drop-shadow(0 8px 20px rgba(0,0,0,.36));
    }
    .brand-copy { display: grid; gap: 3px; }
    .brand-copy strong { font-size: 16px; letter-spacing: .08em; font-weight: 900; }
    .brand-copy span { color: var(--muted); font-size: 10px; letter-spacing: .16em; text-transform: uppercase; }
    .nav { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 7px; }
    .nav-link {
      color: #c9cdc6;
      text-decoration: none;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: .04em;
      padding: 9px 11px;
      border: 1px solid transparent;
      transition: .18s ease;
    }
    a.nav-link:hover { color: white; border-color: var(--line); background: rgba(255,255,255,.025); }
    .nav-link.primary { border-color: rgba(243,107,22,.45); color: #ffd7bc; background: rgba(243,107,22,.07); }
    .nav-link.disabled { color: #5c615c; }

    .hero {
      min-height: 650px;
      padding: 88px 0 62px;
      display: grid;
      grid-template-columns: minmax(0, 1.35fr) minmax(330px, .65fr);
      gap: 72px;
      align-items: center;
      position: relative;
    }
    .hero::after {
      content: "";
      position: absolute;
      left: 0;
      right: 0;
      bottom: 0;
      height: 1px;
      background: linear-gradient(90deg, transparent, rgba(243,107,22,.7), rgba(242,181,44,.35), transparent);
    }
    .kicker { color: var(--orange-2); margin-bottom: 22px; }
    h1 {
      margin: 0;
      max-width: 820px;
      font-family: Impact, Haettenschweiler, "Arial Narrow Bold", sans-serif;
      font-size: clamp(62px, 9.2vw, 142px);
      line-height: .77;
      letter-spacing: -.045em;
      text-transform: uppercase;
      font-weight: 900;
    }
    h1 span { display: block; }
    h1 .accent { color: var(--orange); text-shadow: 0 0 36px rgba(243,107,22,.12); }
    .hero-copy {
      max-width: 700px;
      margin: 29px 0 0;
      color: #aeb3aa;
      font-size: clamp(15px, 1.6vw, 18px);
      line-height: 1.7;
    }
    .chips { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 28px; }
    .chip {
      border: 1px solid var(--line);
      color: #d6d9d2;
      background: rgba(255,255,255,.018);
      padding: 9px 11px;
      font: 750 10px/1 ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      letter-spacing: .11em;
      text-transform: uppercase;
    }

    .system-card {
      position: relative;
      border: 1px solid var(--line-strong);
      background:
        linear-gradient(155deg, rgba(255,255,255,.032), transparent 38%),
        rgba(13,15,13,.86);
      box-shadow: 0 30px 90px rgba(0,0,0,.34);
      overflow: hidden;
    }
    .system-card::before {
      content: "";
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      height: 3px;
      background: linear-gradient(90deg, var(--orange), var(--gold), transparent 72%);
    }
    .system-head {
      padding: 19px 20px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      border-bottom: 1px solid var(--line);
    }
    .online { display: inline-flex; align-items: center; gap: 8px; color: #dff7e4; }
    .pulse { width: 7px; height: 7px; border-radius: 50%; background: var(--green); box-shadow: 0 0 0 5px rgba(141,221,157,.07), 0 0 20px rgba(141,221,157,.45); }
    .system-body { padding: 22px 20px 18px; }
    .system-title { margin: 0 0 17px; font-size: 24px; font-weight: 850; letter-spacing: -.02em; }
    .metric-grid { display: grid; grid-template-columns: 1fr 1fr; border: 1px solid var(--line); }
    .metric { padding: 14px; border-right: 1px solid var(--line); border-bottom: 1px solid var(--line); min-width: 0; }
    .metric:nth-child(even) { border-right: 0; }
    .metric:nth-last-child(-n+2) { border-bottom: 0; }
    .metric small { display: block; color: var(--faint); font: 650 9px/1.2 ui-monospace, monospace; letter-spacing: .12em; text-transform: uppercase; margin-bottom: 6px; }
    .metric strong { display: block; font: 700 12px/1.3 ui-monospace, monospace; color: #e8e8e0; overflow-wrap: anywhere; }
    .terminal { margin-top: 15px; border-top: 1px solid var(--line); padding: 15px 20px; font: 600 10px/1.6 ui-monospace, monospace; color: #7c827b; background: rgba(0,0,0,.16); }
    .terminal .prompt { color: var(--orange-2); }
    .terminal .ok { color: var(--green); }

    section.block { padding: 58px 0; border-bottom: 1px solid var(--line); }
    .section-head { display: flex; justify-content: space-between; align-items: end; gap: 24px; margin-bottom: 25px; }
    .section-head h2 { margin: 7px 0 0; font-size: clamp(28px, 4vw, 52px); letter-spacing: -.035em; }
    .section-head p { max-width: 550px; margin: 0; color: var(--muted); font-size: 13px; line-height: 1.6; }
    .gateways { display: grid; grid-template-columns: repeat(4, 1fr); border: 1px solid var(--line); }
    .gateway {
      position: relative;
      min-height: 190px;
      padding: 20px;
      display: flex;
      flex-direction: column;
      text-decoration: none;
      border-right: 1px solid var(--line);
      background: rgba(255,255,255,.012);
      transition: .2s ease;
    }
    .gateway:last-child { border-right: 0; }
    a.gateway:hover { background: rgba(243,107,22,.045); transform: translateY(-2px); }
    .gateway-index { color: var(--orange-2); font: 700 9px/1 monospace; letter-spacing: .16em; }
    .gateway strong { margin-top: auto; font-size: 21px; }
    .gateway span:not(.gateway-index) { color: var(--muted); margin-top: 4px; font-size: 11px; }
    .gateway b { margin-top: 16px; color: #d6d9d2; font: 700 9px/1 monospace; letter-spacing: .12em; }
    .disabled-card { opacity: .43; }

    .stack { display: grid; grid-template-columns: repeat(4, 1fr); gap: 9px; }
    .stack-card { position: relative; min-height: 230px; padding: 19px; border: 1px solid var(--line); background: rgba(255,255,255,.012); overflow: hidden; }
    .stack-card::before { content: attr(data-stage); position: absolute; right: 13px; top: 8px; color: rgba(244,237,219,.035); font: 900 72px/1 Impact, sans-serif; }
    .stack-card .tag { color: var(--orange-2); }
    .stack-card h3 { margin: 55px 0 8px; font-size: 19px; }
    .stack-card p { margin: 0; color: var(--muted); font-size: 12px; line-height: 1.65; }
    .stack-card code { display: block; margin-top: 15px; color: #777f78; font: 600 9px/1.5 ui-monospace, monospace; white-space: normal; }

    .terrain-strip { height: 96px; position: relative; overflow: hidden; opacity: .8; }
    .terrain-strip svg { width: 100%; height: 100%; }
    footer { min-height: 110px; display: flex; align-items: center; justify-content: space-between; gap: 20px; color: #686e68; font-size: 10px; letter-spacing: .08em; text-transform: uppercase; }
    .footer-principles { display: flex; gap: 14px; flex-wrap: wrap; color: #a8ada6; }
    .footer-principles b { color: var(--orange-2); }

    @media (max-width: 1000px) {
      .hero { grid-template-columns: 1fr; gap: 38px; padding-top: 68px; }
      .system-card { max-width: 620px; }
      .gateways, .stack { grid-template-columns: 1fr 1fr; }
      .gateway:nth-child(2) { border-right: 0; }
      .gateway:nth-child(-n+2) { border-bottom: 1px solid var(--line); }
    }
    @media (max-width: 680px) {
      .shell { width: min(100% - 22px, 1280px); }
      header { align-items: flex-start; flex-direction: column; padding: 17px 0; }
      .brand-logo { width: 50px; height: 50px; }
      .nav { justify-content: flex-start; }
      .hero { min-height: auto; padding: 64px 0 48px; }
      h1 { font-size: clamp(52px, 20vw, 90px); }
      .section-head { align-items: flex-start; flex-direction: column; }
      .gateways, .stack { grid-template-columns: 1fr; }
      .gateway { border-right: 0; border-bottom: 1px solid var(--line); min-height: 150px; }
      .gateway:last-child { border-bottom: 0; }
      .stack-card { min-height: 200px; }
      footer { align-items: flex-start; flex-direction: column; padding: 28px 0; }
    }
    @media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
  </style>
</head>
<body>
  <main class="shell">
    <header>
      <a class="brand-lockup" href="https://www.terrasatch.com" aria-label="TerraSatch home">
        <img class="brand-logo" src="__BRAND_LOGO__" alt="TerraSatch logo">
        <span class="brand-copy"><strong>TERRASATCH</strong><span>Terrain Intelligence · API</span></span>
      </a>
      <nav class="nav" aria-label="API resources">
        <a class="nav-link" href="/health/ready">Health</a>
        __DOCS_LINK__
        <a class="nav-link" href="/openapi.json">OpenAPI</a>
        <a class="nav-link" href="/api/v1/reference">Reference</a>
        <a class="nav-link primary" href="/admin">Admin</a>
      </nav>
    </header>

    <section class="hero">
      <div>
        <div class="kicker micro">Wasatch Front · Utah · Official backend</div>
        <h1><span>Terrain</span><span>Intelligence</span><span class="accent">API.</span></h1>
        <p class="hero-copy">The shared TerraSatch backend for authorized field data, TerraListen radio intelligence, partner applications, and operational decision support across backcountry and remote environments.</p>
        <div class="chips" aria-label="Platform characteristics">
          <span class="chip">AI-Powered</span><span class="chip">Field-Grade</span><span class="chip">Decision Support</span><span class="chip">Partner Ready</span>
        </div>
      </div>

      <aside class="system-card" aria-label="TerraSatch API system status">
        <div class="system-head"><span class="micro">TerraSatch Core</span><span class="online micro"><i class="pulse"></i><span id="status-text">Checking</span></span></div>
        <div class="system-body">
          <h2 class="system-title">Field Intelligence Backend</h2>
          <div class="metric-grid">
            <div class="metric"><small>Environment</small><strong>__ENVIRONMENT__</strong></div>
            <div class="metric"><small>Deployment</small><strong>__DEPLOYMENT__</strong></div>
            <div class="metric"><small>Version</small><strong>__VERSION__</strong></div>
            <div class="metric"><small>Signal</small><strong id="signal-value">QUERYING</strong></div>
          </div>
        </div>
        <div class="terminal"><span class="prompt">$</span> terrasatch deployment check<br><span class="ok" id="terminal-state">● querying /health/ready</span><br>40.7608° N · 111.8910° W · WASATCH<br>UTM 12T · ELEV 4,226 FT · HTTPS/WSS</div>
      </aside>
    </section>

    <section class="block" id="gateways">
      <div class="section-head"><div><span class="micro" style="color:var(--orange-2)">Platform access</span><h2>Developer + Operator Gateways</h2></div><p>Everything needed to validate the live backend, inspect its contract, administer integrations, and connect independent TerraSatch applications.</p></div>
      <div class="gateways">
        <a class="gateway" href="/health/ready"><span class="gateway-index">01</span><strong>Health</strong><span>Database + Redis readiness</span><b>CHECK ↗</b></a>
        __DOCS_CARD__
        <a class="gateway" href="/openapi.json"><span class="gateway-index">03</span><strong>OpenAPI</strong><span>Machine-readable contract</span><b>OPEN ↗</b></a>
        <a class="gateway" href="/admin"><span class="gateway-index">04</span><strong>Admin</strong><span>Organizations, sites, and keys</span><b>LOGIN ↗</b></a>
      </div>
    </section>

    <section class="block" id="stack">
      <div class="section-head"><div><span class="micro" style="color:var(--orange-2)">Field intelligence stack</span><h2>One Backend. Multiple Operations.</h2></div><p>The API is structured so focused demos, pilots, and partner applications can share one secure system without duplicating operational logic.</p></div>
      <div class="stack">
        <article class="stack-card" data-stage="01"><span class="tag micro">Control plane</span><h3>Organizations + Sites</h3><p>Tenant-scoped organizations, operating locations, service credentials, and access boundaries.</p><code>/api/v1/sites · /api/v1/api-keys</code></article>
        <article class="stack-card" data-stage="02"><span class="tag micro">TerraListen</span><h3>Radio Intelligence Inputs</h3><p>Agents, channels, callsigns, authorized transmissions, and preserved source transcripts.</p><code>/agents · /channels · /callsigns · /transmissions</code></article>
        <article class="stack-card" data-stage="03"><span class="tag micro">TerraEngine</span><h3>Structured Events</h3><p>Source-linked operational intelligence designed for mapping, timelines, reporting, and focused workflows.</p><code>/transcripts · /events</code></article>
        <article class="stack-card" data-stage="04"><span class="tag micro">Applications</span><h3>REST + Realtime</h3><p>Stable interfaces for UAC-style demos, partner pilots, field tools, and future edge integrations.</p><code>HTTPS REST · WSS /ws/v1/events</code></article>
      </div>
    </section>

    <div class="terrain-strip" aria-hidden="true">
      <svg viewBox="0 0 1280 100" preserveAspectRatio="none">
        <defs><linearGradient id="terrainLine" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#f36b16" stop-opacity="0"/><stop offset=".18" stop-color="#f36b16"/><stop offset=".52" stop-color="#f2b52c"/><stop offset=".84" stop-color="#f36b16"/><stop offset="1" stop-color="#f36b16" stop-opacity="0"/></linearGradient></defs>
        <path d="M0 87 105 82 172 63 226 78 298 42 355 73 430 29 505 75 565 50 628 77 697 33 760 72 827 46 902 76 981 34 1042 66 1118 49 1280 87" fill="none" stroke="url(#terrainLine)" stroke-width="2"/>
        <g fill="#f4eddb" opacity=".16"><path d="M118 88h20l-10-14h5l-12-17-12 17h5l-10 14h14Z"/><path d="M247 88h28l-14-19h7l-16-23-16 23h7l-14 19h18Z"/><path d="M1020 88h28l-14-19h7l-16-23-16 23h7l-14 19h18Z"/><path d="M1152 88h20l-10-14h5l-12-17-12 17h5l-10 14h14Z"/></g>
      </svg>
    </div>

    <footer><span>TerraSatch · Backcountry + Remote Field Operations</span><span class="footer-principles"><span><b>LISTEN</b></span><span>WATCH</span><span>LEARN</span><span>ADAPT</span></span><span>Receive · Structure · Contextualize · Serve</span></footer>
  </main>

  <script>
    (async () => {
      const statusText = document.getElementById('status-text');
      const signal = document.getElementById('signal-value');
      const terminal = document.getElementById('terminal-state');
      try {
        const response = await fetch('/health/ready', { cache: 'no-store' });
        const payload = await response.json();
        if (response.ok && payload.status === 'healthy') {
          statusText.textContent = 'SYSTEMS ONLINE'; signal.textContent = 'HEALTHY'; terminal.textContent = '● HEALTHY · database + redis ready';
        } else {
          statusText.textContent = 'DEGRADED'; signal.textContent = 'DEGRADED'; terminal.textContent = '● DEGRADED · inspect readiness';
        }
      } catch (_error) {
        statusText.textContent = 'UNAVAILABLE'; signal.textContent = 'UNKNOWN'; terminal.textContent = '● status request failed';
      }
    })();
  </script>
</body>
</html>"""

    for marker, value in replacements.items():
        html = html.replace(marker, value)
    return html
