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
        else (
            '<span class="nav-link disabled" '
            'title="Swagger is disabled in this environment">Swagger Off</span>'
        )
    )
    environment_text = escape(environment)
    deployment_text = escape(deployment)
    version_text = escape(version)

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="theme-color" content="#080908">
  <title>TerraSatch API · Online</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #070807;
      --text: #f4f5f2;
      --muted: #8c918d;
      --line: rgba(255,255,255,.10);
      --orange: #ff7418;
      --orange-bright: #ff9a48;
      --green: #86efac;
    }}
    * {{ box-sizing: border-box; }}
    html, body {{ margin: 0; min-height: 100%; background: var(--bg); color: var(--text); }}
    body {{
      min-height: 100vh;
      overflow-x: hidden;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background:
        radial-gradient(circle at 50% 22%, rgba(255,116,24,.11), transparent 29rem),
        linear-gradient(180deg, #0b0d0b 0%, #070807 68%, #050605 100%);
    }}
    body::before {{
      content: "";
      position: fixed;
      inset: 0;
      pointer-events: none;
      opacity: .17;
      background-image:
        linear-gradient(rgba(255,255,255,.028) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255,255,255,.028) 1px, transparent 1px);
      background-size: 36px 36px;
      mask-image: radial-gradient(circle at center, #000 0%, transparent 76%);
    }}
    .shell {{ width: min(1240px, calc(100% - 32px)); margin: 0 auto; padding: 26px 0 38px; position: relative; z-index: 1; }}
    header {{ display: flex; align-items: center; justify-content: space-between; gap: 18px; margin-bottom: 38px; }}
    .brand {{ display: flex; align-items: center; gap: 11px; font-size: 13px; font-weight: 780; letter-spacing: .12em; }}
    .brand-mark {{ width: 31px; height: 25px; color: var(--orange); }}
    .nav {{ display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; }}
    .nav-link {{ color: #d8ddd9; text-decoration: none; font-size: 12px; padding: 8px 11px; border: 1px solid var(--line); border-radius: 999px; background: rgba(255,255,255,.02); transition: .18s ease; }}
    a.nav-link:hover {{ color: white; border-color: rgba(255,116,24,.55); transform: translateY(-1px); }}
    .nav-link.disabled {{ color: #656b66; cursor: default; }}
    .hero {{ min-height: 620px; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; position: relative; isolation: isolate; }}
    .hero::before {{
      content: "";
      position: absolute;
      width: min(900px, 92vw);
      aspect-ratio: 1.9 / 1;
      border-radius: 50%;
      border: 1px solid rgba(255,116,24,.07);
      box-shadow: 0 0 0 42px rgba(255,116,24,.025), 0 0 0 110px rgba(255,116,24,.012);
      z-index: -1;
      transform: rotate(-5deg);
    }}
    .eyebrow {{ margin-bottom: 23px; color: #a8aea9; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: 11px; letter-spacing: .24em; text-transform: uppercase; }}
    .wordmark-wrap {{ width: min(1120px, 100%); position: relative; padding: 30px 0 36px; }}
    .wordmark {{ display: flex; align-items: center; justify-content: center; gap: clamp(2px, .45vw, 8px); white-space: nowrap; filter: drop-shadow(0 24px 46px rgba(0,0,0,.55)); }}
    .letter {{
      position: relative;
      display: inline-block;
      font-family: Impact, Haettenschweiler, "Arial Narrow Bold", sans-serif;
      font-size: clamp(48px, 9.8vw, 132px);
      font-weight: 900;
      line-height: .78;
      letter-spacing: -.055em;
      color: var(--text);
      transform: skewX(-5deg);
    }}
    .letter.cut::after {{
      content: "";
      position: absolute;
      left: -5%;
      right: -5%;
      top: 44%;
      height: 4px;
      background: var(--bg);
      transform: rotate(-10deg);
      box-shadow: 0 0 0 1px rgba(255,116,24,.08);
    }}
    .peak-a {{ width: clamp(42px, 8.4vw, 112px); height: clamp(48px, 9.1vw, 124px); display: inline-block; position: relative; transform: translateY(-1px) skewX(-4deg); }}
    .peak-a::before, .peak-a::after {{
      content: "";
      position: absolute;
      bottom: 0;
      width: 54%;
      height: 100%;
      background: linear-gradient(180deg, var(--orange-bright), var(--orange));
      filter: drop-shadow(0 0 20px rgba(255,116,24,.16));
    }}
    .peak-a::before {{ left: 0; clip-path: polygon(95% 0, 100% 0, 48% 100%, 0 100%); }}
    .peak-a::after {{ right: 0; clip-path: polygon(0 0, 5% 0, 100% 100%, 52% 100%); }}
    .peak-a .notch {{ position: absolute; left: 22%; right: 22%; bottom: 27%; height: 5px; z-index: 2; background: var(--bg); transform: rotate(-8deg); }}
    .ridge {{ position: absolute; left: 4%; right: 4%; bottom: 3px; height: 45px; pointer-events: none; opacity: .72; }}
    .ridge svg {{ width: 100%; height: 100%; overflow: visible; }}
    .ridge path {{ fill: none; stroke: url(#ridgeGradient); stroke-width: 2; vector-effect: non-scaling-stroke; stroke-linecap: square; stroke-linejoin: bevel; stroke-dasharray: 900; stroke-dashoffset: 900; animation: trace 2.2s ease forwards .15s; }}
    .split-glyph {{ margin: 7px auto 0; width: min(720px, 78vw); height: 52px; position: relative; display: flex; align-items: center; justify-content: center; gap: 12px; }}
    .tri {{ width: 48px; height: 42px; position: relative; }}
    .tri.left {{ clip-path: polygon(0 100%, 100% 0, 100% 100%); background: var(--orange); }}
    .tri.right {{ clip-path: polygon(0 0, 100% 100%, 0 100%); background: rgba(255,255,255,.86); }}
    .beam {{ height: 1px; flex: 1; max-width: 250px; background: linear-gradient(90deg, transparent, rgba(255,116,24,.5)); }}
    .beam.right {{ background: linear-gradient(90deg, rgba(255,255,255,.34), transparent); }}
    .lede {{ max-width: 760px; margin: 22px auto 22px; color: #aeb5af; font-size: clamp(15px, 1.6vw, 18px); line-height: 1.65; }}
    .status-row {{ display: flex; justify-content: center; align-items: center; flex-wrap: wrap; gap: 12px; }}
    .status {{ display: inline-flex; align-items: center; gap: 9px; border: 1px solid rgba(134,239,172,.2); background: rgba(134,239,172,.055); border-radius: 999px; padding: 9px 13px; color: #dbffe6; font-size: 12px; font-weight: 720; letter-spacing: .035em; }}
    .dot {{ width: 7px; height: 7px; border-radius: 50%; background: var(--green); box-shadow: 0 0 0 5px rgba(134,239,172,.06), 0 0 20px rgba(134,239,172,.55); }}
    .status.degraded {{ border-color: rgba(255,116,24,.28); color: #ffd9bb; background: rgba(255,116,24,.055); }}
    .status.degraded .dot {{ background: var(--orange); box-shadow: 0 0 0 5px rgba(255,116,24,.06); }}
    .meta {{ color: #686f69; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: 11px; }}
    .terminal {{ margin-top: 28px; width: min(660px, 96%); padding: 13px 16px; border: 1px solid rgba(255,255,255,.075); border-radius: 14px; background: rgba(255,255,255,.018); color: #8d948e; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: 11px; text-align: left; }}
    .prompt {{ color: var(--orange-bright); }}
    .ok {{ color: var(--green); }}
    .principles {{ margin-top: 16px; border-top: 1px solid var(--line); display: grid; grid-template-columns: repeat(4, 1fr); }}
    .principle {{ padding: 18px 12px; text-align: center; border-right: 1px solid var(--line); }}
    .principle:last-child {{ border-right: 0; }}
    .principle strong {{ display: block; font-size: 11px; letter-spacing: .18em; color: #e7e9e7; margin-bottom: 4px; }}
    .principle span {{ color: #626963; font-size: 11px; }}
    footer {{ margin-top: 28px; color: #565c57; font-size: 11px; display: flex; justify-content: space-between; gap: 12px; flex-wrap: wrap; }}
    @keyframes trace {{ to {{ stroke-dashoffset: 0; }} }}
    @media (max-width: 760px) {{
      header {{ align-items: flex-start; flex-direction: column; }}
      .nav {{ justify-content: flex-start; }}
      .hero {{ min-height: 570px; }}
      .wordmark {{ gap: 1px; }}
      .principles {{ grid-template-columns: 1fr 1fr; }}
      .principle:nth-child(2) {{ border-right: 0; }}
      .principle:nth-child(-n+2) {{ border-bottom: 1px solid var(--line); }}
    }}
    @media (max-width: 480px) {{
      .shell {{ width: min(100% - 20px, 1240px); padding-top: 16px; }}
      .hero {{ min-height: 510px; }}
      .eyebrow {{ letter-spacing: .14em; }}
      .letter {{ font-size: clamp(34px, 12.8vw, 58px); }}
      .peak-a {{ width: clamp(30px, 11vw, 48px); height: clamp(36px, 12vw, 55px); }}
      .split-glyph {{ gap: 7px; }}
      .tri {{ width: 34px; height: 29px; }}
    }}
    @media (prefers-reduced-motion: reduce) {{ * {{ animation: none !important; transition: none !important; }} }}
  </style>
</head>
<body>
  <main class="shell">
    <header>
      <div class="brand">
        <svg class="brand-mark" viewBox="0 0 48 36" fill="none" aria-hidden="true">
          <path d="M2 32 24 3v29H2Z" fill="currentColor"/>
          <path d="M46 32 27 7v25h19Z" fill="rgba(255,255,255,.82)"/>
        </svg>
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
      <div class="eyebrow">Official field intelligence backend · signal online</div>

      <div class="wordmark-wrap" aria-label="TerraSatch geometric mountain wordmark">
        <div class="wordmark" role="img" aria-label="TERRASATCH">
          <span class="letter cut">T</span>
          <span class="letter">E</span>
          <span class="letter cut">R</span>
          <span class="letter">R</span>
          <span class="peak-a" aria-label="A"><span class="notch"></span></span>
          <span class="letter cut">S</span>
          <span class="peak-a" aria-label="A"><span class="notch"></span></span>
          <span class="letter">T</span>
          <span class="letter cut">C</span>
          <span class="letter">H</span>
        </div>
        <div class="ridge" aria-hidden="true">
          <svg viewBox="0 0 1000 80" preserveAspectRatio="none">
            <defs>
              <linearGradient id="ridgeGradient" x1="0" y1="0" x2="1" y2="0">
                <stop offset="0" stop-color="rgba(255,255,255,0)"/>
                <stop offset=".24" stop-color="#ff7418"/>
                <stop offset=".5" stop-color="#ffb071"/>
                <stop offset=".76" stop-color="#ff7418"/>
                <stop offset="1" stop-color="rgba(255,255,255,0)"/>
              </linearGradient>
            </defs>
            <path d="M0 65 150 59 236 32 300 52 384 18 456 50 527 10 612 55 698 27 765 53 842 34 1000 65"/>
          </svg>
        </div>
      </div>

      <div class="split-glyph" aria-hidden="true">
        <div class="beam"></div>
        <div class="tri left"></div>
        <div class="tri right"></div>
        <div class="beam right"></div>
      </div>

      <p class="lede">A shared backend for authorized operational data, partner applications, and the evolving TerraListen radio intelligence pipeline.</p>

      <div class="status-row">
        <div class="status" id="api-status"><span class="dot"></span><span id="status-text">Checking systems…</span></div>
        <span class="meta">{environment_text} · {deployment_text} · v{version_text}</span>
      </div>

      <div class="terminal"><span class="prompt">$</span> terrasatch deployment check &nbsp; <span class="ok" id="terminal-state">● querying /health/ready</span></div>
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
