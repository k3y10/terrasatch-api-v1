"""Lightweight branded landing page for the public TerraSatch API host."""

from __future__ import annotations

from html import escape


def build_landing_page(
    *,
    environment: str,
    deployment: str,
    version: str,
    docs_enabled: bool,
) -> str:
    """Return a dependency-free status landing page without exposing sensitive data."""

    docs_link = (
        '<a class="nav-link" href="/docs">Swagger Docs</a>'
        if docs_enabled
        else '<span class="nav-link disabled" title="Swagger is disabled in this environment">Swagger Off</span>'
    )
    environment_text = escape(environment)
    deployment_text = escape(deployment)
    version_text = escape(version)

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="theme-color" content="#0b0d0c">
  <title>TerraSatch API · Online</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #090b0a;
      --panel: rgba(20, 24, 21, .72);
      --panel-strong: rgba(26, 31, 27, .9);
      --line: rgba(255,255,255,.10);
      --muted: #a9b0aa;
      --text: #f4f6f4;
      --orange: #ff7a1a;
      --orange-soft: #ffad6d;
      --green: #86efac;
      --shadow: 0 28px 80px rgba(0,0,0,.42);
    }}
    * {{ box-sizing: border-box; }}
    html, body {{ margin: 0; min-height: 100%; background: var(--bg); color: var(--text); }}
    body {{
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      min-height: 100vh;
      overflow-x: hidden;
      background:
        radial-gradient(circle at 76% 16%, rgba(255,122,26,.16), transparent 32rem),
        radial-gradient(circle at 18% 82%, rgba(73,93,78,.22), transparent 36rem),
        linear-gradient(180deg, #0c0f0d 0%, #080a09 72%);
    }}
    body::before {{
      content: "";
      position: fixed;
      inset: 0;
      pointer-events: none;
      opacity: .16;
      background-image: linear-gradient(rgba(255,255,255,.025) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.025) 1px, transparent 1px);
      background-size: 34px 34px;
      mask-image: linear-gradient(to bottom, black, transparent 78%);
    }}
    .shell {{ width: min(1180px, calc(100% - 32px)); margin: 0 auto; padding: 28px 0 42px; position: relative; z-index: 1; }}
    header {{ display: flex; align-items: center; justify-content: space-between; gap: 18px; margin-bottom: 48px; }}
    .brand {{ display: flex; align-items: center; gap: 12px; font-weight: 760; letter-spacing: .04em; }}
    .mark {{
      width: 38px; height: 38px; border: 1px solid rgba(255,122,26,.5); border-radius: 12px;
      display: grid; place-items: center; background: rgba(255,122,26,.08); color: var(--orange);
      box-shadow: inset 0 0 24px rgba(255,122,26,.08);
    }}
    .mark svg {{ width: 25px; height: 25px; }}
    .nav {{ display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; }}
    .nav-link {{ color: #dfe5e0; text-decoration: none; font-size: 13px; padding: 9px 12px; border: 1px solid var(--line); border-radius: 999px; background: rgba(255,255,255,.025); transition: .18s ease; }}
    a.nav-link:hover {{ border-color: rgba(255,122,26,.55); color: white; transform: translateY(-1px); }}
    .nav-link.disabled {{ color: #737a75; cursor: default; }}
    .hero {{ display: grid; grid-template-columns: minmax(0, 1.05fr) minmax(360px, .95fr); gap: 46px; align-items: center; min-height: 570px; }}
    .eyebrow {{ color: var(--orange-soft); text-transform: uppercase; letter-spacing: .18em; font-size: 12px; font-weight: 760; margin-bottom: 18px; }}
    h1 {{ font-size: clamp(50px, 8vw, 92px); line-height: .9; letter-spacing: -.065em; margin: 0; max-width: 780px; }}
    h1 span {{ display: block; color: var(--orange); }}
    .lede {{ color: #bdc4be; font-size: clamp(17px, 2vw, 20px); line-height: 1.6; max-width: 660px; margin: 28px 0 26px; }}
    .status-row {{ display: flex; align-items: center; flex-wrap: wrap; gap: 12px; }}
    .status {{ display: inline-flex; align-items: center; gap: 9px; border: 1px solid rgba(134,239,172,.2); background: rgba(134,239,172,.06); border-radius: 999px; padding: 10px 14px; color: #d9ffe5; font-size: 13px; font-weight: 700; }}
    .dot {{ width: 8px; height: 8px; border-radius: 999px; background: var(--green); box-shadow: 0 0 0 5px rgba(134,239,172,.08), 0 0 24px rgba(134,239,172,.65); }}
    .status.degraded {{ border-color: rgba(255,173,109,.3); color: #ffe0c7; background: rgba(255,122,26,.07); }}
    .status.degraded .dot {{ background: var(--orange); box-shadow: 0 0 0 5px rgba(255,122,26,.08); }}
    .meta {{ font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; color: #858d87; font-size: 12px; }}
    .art-card {{
      position: relative; min-height: 520px; overflow: hidden; border: 1px solid var(--line); border-radius: 30px;
      background: linear-gradient(155deg, rgba(255,255,255,.055), rgba(255,255,255,.015)); box-shadow: var(--shadow);
      isolation: isolate;
    }}
    .art-card::after {{ content: ""; position: absolute; inset: 0; box-shadow: inset 0 0 0 1px rgba(255,255,255,.025); border-radius: inherit; pointer-events: none; }}
    .sun {{ position: absolute; width: 220px; height: 220px; border-radius: 50%; right: -35px; top: -26px; background: radial-gradient(circle at 35% 35%, #ffb46e, #ff7418 44%, #c44200 74%, transparent 75%); opacity: .9; filter: saturate(.9); z-index: -3; }}
    .mountains {{ position: absolute; inset: auto 0 0; width: 100%; height: 82%; z-index: -2; }}
    .squatch {{ position: absolute; left: 53%; bottom: 83px; transform: translateX(-50%); width: 100px; filter: drop-shadow(0 16px 20px rgba(0,0,0,.5)); opacity: .98; }}
    .terminal {{ position: absolute; left: 24px; right: 24px; bottom: 22px; padding: 17px 18px; border-radius: 17px; border: 1px solid rgba(255,255,255,.09); background: rgba(6,8,7,.76); backdrop-filter: blur(16px); font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: 12px; color: #c7cec8; }}
    .terminal .prompt {{ color: var(--orange-soft); }}
    .terminal .ok {{ color: var(--green); }}
    .art-label {{ position: absolute; top: 24px; left: 25px; right: 25px; display: flex; justify-content: space-between; align-items: center; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: 11px; letter-spacing: .08em; color: rgba(255,255,255,.58); text-transform: uppercase; }}
    .signal {{ display: inline-flex; gap: 3px; align-items: flex-end; height: 15px; }}
    .signal i {{ width: 2px; display: block; border-radius: 2px; background: var(--orange); animation: pulse 1.2s ease-in-out infinite alternate; }}
    .signal i:nth-child(1) {{ height: 4px; }} .signal i:nth-child(2) {{ height: 8px; animation-delay: .15s; }} .signal i:nth-child(3) {{ height: 13px; animation-delay: .3s; }} .signal i:nth-child(4) {{ height: 7px; animation-delay: .45s; }}
    @keyframes pulse {{ to {{ opacity: .35; transform: scaleY(.68); }} }}
    .principles {{ margin-top: 50px; padding-top: 22px; border-top: 1px solid var(--line); display: grid; grid-template-columns: repeat(4, 1fr); gap: 18px; }}
    .principle strong {{ display: block; color: #f6f8f6; font-size: 12px; letter-spacing: .12em; margin-bottom: 5px; }}
    .principle span {{ color: #717a73; font-size: 12px; }}
    footer {{ margin-top: 44px; color: #626a64; font-size: 12px; display: flex; justify-content: space-between; gap: 12px; flex-wrap: wrap; }}
    @media (max-width: 860px) {{
      header {{ align-items: flex-start; }} .hero {{ grid-template-columns: 1fr; min-height: auto; }} .art-card {{ min-height: 430px; }}
      .principles {{ grid-template-columns: repeat(2, 1fr); }} h1 {{ font-size: clamp(52px, 15vw, 82px); }}
    }}
    @media (max-width: 540px) {{
      .shell {{ width: min(100% - 22px, 1180px); padding-top: 16px; }} header {{ flex-direction: column; margin-bottom: 34px; }}
      .nav {{ justify-content: flex-start; }} .art-card {{ min-height: 390px; border-radius: 22px; }} .principles {{ grid-template-columns: 1fr 1fr; }}
      .terminal {{ left: 14px; right: 14px; bottom: 14px; }}
    }}
    @media (prefers-reduced-motion: reduce) {{ * {{ animation: none !important; transition: none !important; }} }}
  </style>
</head>
<body>
  <main class="shell">
    <header>
      <div class="brand">
        <span class="mark" aria-hidden="true">
          <svg viewBox="0 0 32 32" fill="none"><path d="M3 25.5 11.2 13l4.3 6.2L20.7 9 29 25.5H3Z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><path d="m11.2 13 2.4 3.5 1.9-2.8 2.1 3.5 3.1-8.2" stroke="currentColor" stroke-width="1.35" opacity=".7"/></svg>
        </span>
        <span>TERRASATCH API</span>
      </div>
      <nav class="nav" aria-label="API resources">
        <a class="nav-link" href="/health/ready">Health</a>
        {docs_link}
        <a class="nav-link" href="/openapi.json">OpenAPI</a>
        <a class="nav-link" href="/api/v1/reference">Reference</a>
        <a class="nav-link" href="/admin">Admin</a>
      </nav>
    </header>

    <section class="hero">
      <div>
        <div class="eyebrow">Field intelligence · live backend</div>
        <h1>LISTEN.<span>LEARN. ADAPT.</span></h1>
        <p class="lede">The official TerraSatch field-intelligence API is online. A shared backend for authorized operational data, partner applications, and the evolving TerraListen radio intelligence pipeline.</p>
        <div class="status-row">
          <div class="status" id="api-status"><span class="dot"></span><span id="status-text">Checking systems…</span></div>
          <span class="meta">{environment_text} · {deployment_text} · v{version_text}</span>
        </div>
      </div>

      <div class="art-card" aria-label="Stylized Wasatch mountain scene with Sasquatch silhouette">
        <div class="sun"></div>
        <div class="art-label"><span>Wasatch signal / 001</span><span class="signal"><i></i><i></i><i></i><i></i></span></div>
        <svg class="mountains" viewBox="0 0 620 520" preserveAspectRatio="none" aria-hidden="true">
          <defs>
            <linearGradient id="ridgeA" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#4f5e52"/><stop offset="1" stop-color="#182019"/></linearGradient>
            <linearGradient id="ridgeB" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#28342b"/><stop offset="1" stop-color="#0d120f"/></linearGradient>
          </defs>
          <path d="M0 300 74 214l41 41 74-125 54 82 66-127 74 139 47-63 55 87 55-53 80 105v220H0Z" fill="url(#ridgeA)"/>
          <path d="m74 214 41 41 74-125 31 47 23 35 66-127 28 52 46 87 47-63 19 30 36 57 55-53 80 105" fill="none" stroke="rgba(255,255,255,.23)" stroke-width="2"/>
          <path d="M0 390 65 352l67 30 68-80 54 57 71-92 66 95 58-53 72 76 99-73v208H0Z" fill="url(#ridgeB)"/>
          <path d="M0 470c95-35 158 9 252-18 89-25 172 24 368-27v95H0Z" fill="#090d0a"/>
        </svg>
        <svg class="squatch" viewBox="0 0 110 220" aria-hidden="true">
          <path fill="#070908" d="M53 6c17 0 28 13 27 29-1 8-4 13-9 18 8 9 12 21 12 35 0 18-6 31-13 43l6 30 18 43-18 9-24-42-6-1-10 43-19-5 7-47 7-31c-8-12-13-27-12-45 1-17 7-29 17-37-7-5-11-13-11-23C25 13 37 6 53 6Zm-25 57L9 91l11 7 19-24-11-11Zm53 3-5 13 23 18 8-12-26-19Z"/>
          <path d="M37 38c7 5 26 6 33-1" fill="none" stroke="rgba(255,122,26,.42)" stroke-width="2" stroke-linecap="round"/>
        </svg>
        <div class="terminal"><span class="prompt">$</span> terrasatch deployment check<br><span class="ok" id="terminal-state">● querying /health/ready</span></div>
      </div>
    </section>

    <section class="principles" aria-label="TerraSatch principles">
      <div class="principle"><strong>LISTEN</strong><span>Authorized field inputs</span></div>
      <div class="principle"><strong>WATCH</strong><span>Operational context</span></div>
      <div class="principle"><strong>LEARN</strong><span>Structured intelligence</span></div>
      <div class="principle"><strong>ADAPT</strong><span>Stable client APIs</span></div>
    </section>

    <footer><span>TerraSatch · Backcountry and remote field operations</span><span>Receive · Structure · Contextualize · Serve</span></footer>
  </main>
  <script>
    (async () => {{
      const badge = document.getElementById('api-status');
      const text = document.getElementById('status-text');
      const terminal = document.getElementById('terminal-state');
      try {{
        const response = await fetch('/health/ready', {{ cache: 'no-store' }});
        const payload = await response.json();
        if (response.ok && payload.status === 'healthy') {{
          text.textContent = 'API ONLINE · SYSTEMS HEALTHY';
          terminal.textContent = '● HEALTHY · database + redis ready';
        }} else {{
          badge.classList.add('degraded');
          text.textContent = 'API ONLINE · DEGRADED';
          terminal.textContent = '● DEGRADED · inspect readiness';
        }}
      }} catch (_error) {{
        badge.classList.add('degraded');
        text.textContent = 'STATUS CHECK UNAVAILABLE';
        terminal.textContent = '● status request failed';
      }}
    }})();
  </script>
</body>
</html>"""
