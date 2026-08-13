"""Lightweight branded landing page for the public TerraSatch API host."""

from __future__ import annotations

from html import escape


_BRAND_LOGO_URL = "https://www.terrasatch.com/assets/terrasatch-logo-BEpaywXF.png"


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
    .coordinates { margin-top: 16px; color: #676e66; font: 650 9px/1.6 ui-monospace, monospace; letter-spacing: .07em; }
    .terminal {
      margin-top: 16px;
      border: 1px solid var(--line);
      padding: 12px 13px;
      font: 650 10px/1.55 ui-monospace, monospace;
      color: #8e958c;
      background: #090a09;
    }
    .terminal .prompt { color: var(--orange-2); }
    .terminal .ok { color: var(--green); }

    .section { padding: 68px 0; }
    .section-heading { display: grid; grid-template-columns: 1fr auto; gap: 22px; align-items: end; margin-bottom: 28px; }
    .section-heading .label { color: var(--orange-2); margin-bottom: 10px; }
    .section-heading h2 { margin: 0; font-size: clamp(30px, 4.4vw, 58px); line-height: .95; letter-spacing: -.04em; text-transform: uppercase; }
    .section-heading p { max-width: 480px; color: var(--muted); margin: 0; font-size: 13px; line-height: 1.65; text-align: right; }

    .gateways { display: grid; grid-template-columns: repeat(4, 1fr); border: 1px solid var(--line); }
    .gateway {
      min-height: 190px;
      padding: 19px;
      text-decoration: none;
      display: flex;
      flex-direction: column;
      border-right: 1px solid var(--line);
      background: rgba(255,255,255,.012);
      transition: .18s ease;
    }
    .gateway:last-child { border-right: 0; }
    a.gateway:hover { background: rgba(243,107,22,.055); transform: translateY(-2px); }
    .gateway-index { color: var(--orange); font: 800 10px/1 ui-monospace, monospace; letter-spacing: .15em; }
    .gateway strong { margin-top: 39px; font-size: 18px; }
    .gateway span:not(.gateway-index) { margin-top: 7px; color: var(--muted); font-size: 12px; line-height: 1.45; }
    .gateway b { margin-top: auto; color: #727970; font: 700 9px/1 ui-monospace, monospace; letter-spacing: .15em; }
    .disabled-card { opacity: .45; }

    .stack-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }
    .stack-card { min-height: 220px; border: 1px solid var(--line); background: rgba(255,255,255,.015); padding: 19px; position: relative; }
    .stack-card::after { content: ""; position: absolute; left: 19px; right: 19px; top: 52px; height: 1px; background: var(--line); }
    .stack-card .number { color: var(--orange); }
    .stack-card h3 { margin: 42px 0 10px; font-size: 17px; }
    .stack-card p { margin: 0; color: var(--muted); font-size: 12px; line-height: 1.6; }
    .stack-card ul { list-style: none; padding: 0; margin: 19px 0 0; display: grid; gap: 7px; }
    .stack-card li { color: #c3c7c0; font: 650 10px/1.4 ui-monospace, monospace; }
    .stack-card li::before { content: "↳ "; color: var(--orange); }

    .forest-line { height: 82px; margin-top: 22px; opacity: .5; }
    .forest-line svg { width: 100%; height: 100%; }
    .forest-line path { fill: rgba(244,237,219,.14); }
    .forest-line .signal { fill: var(--orange); }

    footer {
      padding: 28px 0 38px;
      border-top: 1px solid var(--line);
      display: flex;
      justify-content: space-between;
      gap: 20px;
      color: #656b64;
      font-size: 10px;
      letter-spacing: .08em;
      text-transform: uppercase;
    }

    @media (max-width: 980px) {
      .hero { grid-template-columns: 1fr; gap: 45px; padding-top: 62px; }
      .hero-copy { max-width: 760px; }
      .system-card { max-width: 650px; }
      .gateways, .stack-grid { grid-template-columns: 1fr 1fr; }
      .gateway:nth-child(2) { border-right: 0; }
      .gateway:nth-child(-n+2) { border-bottom: 1px solid var(--line); }
    }
    @media (max-width: 700px) {
      header { align-items: flex-start; padding: 17px 0; flex-direction: column; }
      .nav { justify-content: flex-start; }
      .hero { min-height: 0; padding: 56px 0; }
      h1 { font-size: clamp(58px, 21vw, 96px); }
      .section-heading { grid-template-columns: 1fr; }
      .section-heading p { text-align: left; }
      .gateways, .stack-grid { grid-template-columns: 1fr; }
      .gateway { border-right: 0; border-bottom: 1px solid var(--line); min-height: 155px; }
      .gateway:last-child { border-bottom: 0; }
      .stack-card { min-height: 190px; }
      footer { flex-direction: column; }
    }
    @media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
  </style>
</head>
<body>
  <main class="shell">
    <header>
      <a class="brand-lockup" href="https://www.terrasatch.com" aria-label="TerraSatch main website">
        <img class="brand-logo" src="__BRAND_LOGO__" alt="TerraSatch logo">
        <span class="brand-copy"><strong>TERRASATCH</strong><span>Terrain Intelligence · API</span></span>
      </a>
      <nav class="nav" aria-label="API resources">
        <a class="nav-link" href="https://www.terrasatch.com">Main Site</a>
        <a class="nav-link" href="/health/ready">Health</a>
        __DOCS_LINK__
        <a class="nav-link" href="/openapi.json">OpenAPI</a>
        <a class="nav-link primary" href="/admin">Admin Console</a>
      </nav>
    </header>

    <section class="hero">
      <div>
        <div class="kicker micro">Wasatch Front · Utah · Official Backend</div>
        <h1><span>Terrain</span><span>Intelligence</span><span class="accent">API.</span></h1>
        <p class="hero-copy">The integration layer behind TerraSatch field intelligence. Authorized partner applications, operational data, TerraListen radio workflows, and structured events share one secure backend.</p>
        <div class="chips">
          <span class="chip">AI-Powered</span>
          <span class="chip">Field-Grade</span>
          <span class="chip">Decision Support</span>
          <span class="chip">Partner Ready</span>
        </div>
      </div>

      <aside class="system-card" aria-label="TerraSatch API system status">
        <div class="system-head">
          <span class="micro">System Status</span>
          <span class="online micro" id="api-status"><i class="pulse"></i><span id="status-text">Checking</span></span>
        </div>
        <div class="system-body">
          <h2 class="system-title">TerraSatch Core</h2>
          <div class="metric-grid">
            <div class="metric"><small>Environment</small><strong>__ENVIRONMENT__</strong></div>
            <div class="metric"><small>Deployment</small><strong>__DEPLOYMENT__</strong></div>
            <div class="metric"><small>Release</small><strong>v__VERSION__</strong></div>
            <div class="metric"><small>Transport</small><strong>HTTPS · WSS</strong></div>
          </div>
          <div class="coordinates">40.7608° N &nbsp;|&nbsp; 111.8910° W &nbsp;|&nbsp; ELV 4,226 FT &nbsp;|&nbsp; GRID UTM 12T</div>
          <div class="terminal"><span class="prompt">$</span> terrasatch deployment check<br><span class="ok" id="terminal-state">● querying /health/ready</span></div>
        </div>
      </aside>
    </section>

    <section class="section">
      <div class="section-heading">
        <div><div class="label micro">Developer Access</div><h2>Platform Gateways</h2></div>
        <p>Direct entry points for system health, interactive testing, machine-readable contracts, and operator administration.</p>
      </div>
      <div class="gateways">
        <a class="gateway" href="/health/ready"><span class="gateway-index">01</span><strong>Health</strong><span>Database + Redis readiness</span><b>CHECK ↗</b></a>
        __DOCS_CARD__
        <a class="gateway" href="/openapi.json"><span class="gateway-index">03</span><strong>OpenAPI</strong><span>Machine-readable API contract</span><b>VIEW JSON ↗</b></a>
        <a class="gateway" href="/admin"><span class="gateway-index">04</span><strong>Admin</strong><span>Organizations, sites + API access</span><b>SECURE ENTRY ↗</b></a>
      </div>
    </section>

    <section class="section">
      <div class="section-heading">
        <div><div class="label micro">Modular Architecture</div><h2>Field Intelligence Stack</h2></div>
        <p>The API mirrors TerraSatch's broader architecture: secure inputs are structured, contextualized, persisted, and served back to operational tools.</p>
      </div>
      <div class="stack-grid">
        <article class="stack-card"><span class="number micro">01 · Control</span><h3>Organizations + Sites</h3><p>Tenant-aware configuration for partner pilots, operational areas, and separate field deployments.</p><ul><li>API keys</li><li>Scopes</li><li>Site isolation</li></ul></article>
        <article class="stack-card"><span class="number micro">02 · Signal</span><h3>TerraListen Inputs</h3><p>Authorized transmissions enter a common ingestion path designed for future radio, audio, edge, and SDR sources.</p><ul><li>Transmissions</li><li>Channels</li><li>Callsigns</li></ul></article>
        <article class="stack-card"><span class="number micro">03 · Intelligence</span><h3>Structured Events</h3><p>Source-preserving transcripts are transformed into normalized operational events with provenance and context.</p><ul><li>Transcripts</li><li>TerraEngine</li><li>Event records</li></ul></article>
        <article class="stack-card"><span class="number micro">04 · Serve</span><h3>REST + Realtime</h3><p>Partner demos consume one stable interface rather than maintaining separate mock intelligence pipelines.</p><ul><li>REST API</li><li>OpenAPI</li><li>WebSocket</li></ul></article>
      </div>

      <div class="forest-line" aria-hidden="true">
        <svg viewBox="0 0 1200 90" preserveAspectRatio="none">
          <path d="M0 82 56 82 78 55 89 68 106 40 123 68 136 52 155 82 222 82 249 48 260 65 281 27 305 64 319 47 342 82 410 82 434 58 447 71 465 45 486 70 499 57 520 82 681 82 706 50 718 66 740 33 762 66 778 49 798 82 866 82 891 57 904 70 924 41 948 69 961 55 983 82 1055 82 1082 52 1096 68 1117 31 1140 68 1155 48 1180 82Z"/>
          <path class="signal" d="M565 82 588 52 599 67 617 40 636 67 649 54 670 82Z"/>
        </svg>
      </div>
    </section>

    <footer><span>TerraSatch · Terrain Intelligence · Salt Lake City, UT</span><span>Listen · Watch · Learn · Adapt</span></footer>
  </main>

  <script>
    (async () => {
      const status = document.getElementById('status-text');
      const terminal = document.getElementById('terminal-state');
      try {
        const response = await fetch('/health/ready', { cache: 'no-store' });
        const payload = await response.json();
        if (response.ok && payload.status === 'healthy') {
          status.textContent = 'ONLINE';
          terminal.textContent = '● HEALTHY · database + redis ready';
        } else {
          status.textContent = 'DEGRADED';
          terminal.textContent = '● DEGRADED · inspect readiness';
          document.querySelector('.pulse').style.background = 'var(--orange)';
        }
      } catch (_error) {
        status.textContent = 'UNKNOWN';
        terminal.textContent = '● status request failed';
        document.querySelector('.pulse').style.background = 'var(--orange)';
      }
    })();
  </script>
</body>
</html>"""

    for placeholder, value in replacements.items():
        html = html.replace(placeholder, value)
    return html
