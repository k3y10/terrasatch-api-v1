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
    """Return a clean, viewport-fixed TerraListen operations console."""

    docs_nav = (
        '<a class="top-link" href="/docs">Docs</a>'
        if docs_enabled
        else '<span class="top-link disabled">Docs Off</span>'
    )

    replacements = {
        "__ENVIRONMENT__": escape(environment.upper()),
        "__DEPLOYMENT__": escape(deployment),
        "__VERSION__": escape(version),
        "__DOCS_NAV__": docs_nav,
        "__BRAND_LOGO__": _BRAND_LOGO_URL,
        "__BRAND_FALLBACK__": _BRAND_LOGO_FALLBACK_URL,
    }

    html = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
  <meta name="theme-color" content="#090d0f">
  <meta name="description" content="TerraSatch TerraListen receive-only radio intelligence console for field operations.">
  <title>TerraSatch · TerraListen Radio Console</title>
  <style>
    :root{
      color-scheme:dark;
      --bg:#090d0f;
      --bg-soft:#0d1215;
      --surface:#101619;
      --surface-2:#141b1f;
      --surface-3:#0c1114;
      --text:#f2f4f3;
      --muted:#8e999f;
      --muted-2:#657078;
      --line:rgba(255,255,255,.09);
      --line-strong:rgba(255,255,255,.14);
      --orange:#f47a20;
      --orange-soft:rgba(244,122,32,.12);
      --green:#70de89;
      --green-soft:rgba(112,222,137,.10);
      --shadow:0 20px 60px rgba(0,0,0,.28);
      --radius:16px;
    }
    *{box-sizing:border-box}
    html,body{width:100%;height:100%;margin:0;overflow:hidden}
    body{
      color:var(--text);
      font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
      background:
        radial-gradient(circle at 68% -20%,rgba(244,122,32,.10),transparent 34%),
        linear-gradient(180deg,#0a0f12 0%,#070a0c 100%);
    }
    a{color:inherit}
    .mono{font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace}
    .app{height:100dvh;min-height:0;display:grid;grid-template-rows:76px minmax(0,1fr) 36px;overflow:hidden}

    header{
      display:grid;
      grid-template-columns:minmax(240px,1fr) auto auto;
      align-items:center;
      gap:24px;
      padding:0 clamp(18px,2.4vw,40px);
      border-bottom:1px solid var(--line);
      background:rgba(9,13,15,.88);
      backdrop-filter:blur(18px);
      z-index:5;
    }
    .brand{display:flex;align-items:center;gap:12px;min-width:0;text-decoration:none}
    .brand img{width:54px;height:54px;object-fit:contain;filter:drop-shadow(0 0 16px rgba(244,122,32,.12))}
    .brand-copy{display:grid;gap:3px;line-height:1}
    .brand-copy strong{font-size:16px;letter-spacing:.08em}
    .brand-copy b{font-size:13px;letter-spacing:.14em;color:var(--orange)}
    .brand-copy small{font:700 9px/1.2 ui-monospace,monospace;letter-spacing:.12em;color:var(--muted-2);text-transform:uppercase}
    .top-nav{display:flex;align-items:center;gap:22px}
    .top-link{font-size:12px;font-weight:750;letter-spacing:.04em;color:#b4bcc0;text-decoration:none;white-space:nowrap}
    .top-link:hover{color:var(--orange)}
    .top-link.disabled{opacity:.38}
    .header-state{display:flex;align-items:center;gap:12px}
    .system-pill{display:flex;align-items:center;gap:8px;padding:9px 13px;border:1px solid rgba(112,222,137,.24);border-radius:999px;background:var(--green-soft);color:var(--green);font:800 11px/1 ui-monospace,monospace;letter-spacing:.05em;white-space:nowrap}
    .dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:currentColor;box-shadow:0 0 10px currentColor}
    .environment{padding:9px 11px;border:1px solid var(--line);border-radius:999px;color:var(--muted);font:800 10px/1 ui-monospace,monospace;letter-spacing:.08em}

    .workspace{
      min-height:0;
      overflow:hidden;
      display:grid;
      grid-template-columns:minmax(0,1fr) minmax(280px,330px);
      gap:16px;
      padding:18px clamp(18px,2.4vw,40px);
    }
    .primary{min-width:0;min-height:0;display:grid;grid-template-rows:minmax(0,1.15fr) minmax(220px,.85fr);gap:16px}
    .rail{min-width:0;min-height:0;display:grid;grid-template-rows:auto auto 1fr auto;gap:12px}
    .card{min-width:0;min-height:0;border:1px solid var(--line);border-radius:var(--radius);background:linear-gradient(180deg,rgba(18,24,28,.96),rgba(12,17,20,.96));box-shadow:var(--shadow)}

    .receiver{padding:24px;display:grid;grid-template-rows:auto minmax(100px,1fr) auto;gap:16px;overflow:hidden}
    .receiver-head{display:flex;align-items:flex-start;justify-content:space-between;gap:24px}
    .receiver-title h1{margin:0;font-size:clamp(30px,2.25vw,42px);line-height:1.02;letter-spacing:-.035em}
    .receiver-title p{margin:9px 0 0;color:#aeb7bb;font-size:15px;line-height:1.45}
    .receiver-state{min-width:250px;padding:14px 16px;border:1px solid var(--line-strong);border-radius:13px;background:rgba(255,255,255,.025)}
    .receiver-state strong{display:flex;align-items:center;gap:9px;color:var(--green);font-size:16px;letter-spacing:.02em}
    .receiver-state span{display:block;margin-top:6px;color:#b2babd;font-size:13px}

    .spectrum{min-height:0;position:relative;overflow:hidden;border:1px solid var(--line);border-radius:13px;background:linear-gradient(180deg,#0a1013,#080c0f)}
    .spectrum:before{content:"";position:absolute;inset:0;opacity:.42;background-image:linear-gradient(rgba(255,255,255,.03) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.03) 1px,transparent 1px);background-size:34px 34px}
    .spectrum-head{position:relative;z-index:2;display:flex;align-items:center;justify-content:space-between;padding:13px 15px 0;color:var(--muted);font:800 10px/1 ui-monospace,monospace;letter-spacing:.1em;text-transform:uppercase}
    .live-label{display:flex;align-items:center;gap:7px;color:var(--green)}
    .wave{position:absolute;z-index:1;left:14px;right:14px;bottom:30px;height:calc(100% - 70px);display:flex;align-items:end;gap:clamp(1px,.18vw,3px);overflow:hidden;contain:layout paint}
    .wave i{flex:1 1 0;width:auto;min-width:0;height:var(--h);max-height:86%;border-radius:3px 3px 0 0;background:linear-gradient(180deg,#ffad59 0%,var(--orange) 46%,#7d3611 100%);opacity:.8;transform-origin:50% 100%;animation:pulse 1.9s ease-in-out infinite alternate;animation-delay:var(--d);will-change:transform,opacity}
    .spectrum-foot{position:absolute;z-index:2;left:15px;right:15px;bottom:10px;display:flex;justify-content:space-between;color:var(--muted-2);font:700 10px/1 ui-monospace,monospace;letter-spacing:.05em}

    .receiver-meta{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px}
    .meta{min-width:0;padding:10px 12px;border:1px solid var(--line);border-radius:11px;background:rgba(255,255,255,.018)}
    .meta span{display:block;color:var(--muted-2);font:800 9px/1 ui-monospace,monospace;letter-spacing:.09em;text-transform:uppercase}
    .meta b{display:block;margin-top:6px;color:#dfe4e2;font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
    .meta b.orange{color:var(--orange)}
    .meta b.green{color:var(--green)}

    .activity{overflow:hidden;display:grid;grid-template-rows:54px minmax(0,1fr)}
    .activity-head{display:flex;align-items:center;justify-content:space-between;padding:0 18px;border-bottom:1px solid var(--line)}
    .activity-head strong{font-size:13px;letter-spacing:.035em}
    .activity-head span{color:var(--muted);font-size:11px}
    .activity-list{min-height:0;display:grid;grid-template-rows:repeat(4,minmax(0,1fr))}
    .activity-row{min-height:0;display:grid;grid-template-columns:120px minmax(0,1fr) auto;align-items:center;gap:16px;padding:10px 18px;border-bottom:1px solid rgba(255,255,255,.06)}
    .activity-row:last-child{border-bottom:0}
    .activity-source{display:flex;align-items:center;gap:9px;color:#c9d0d2;font-size:12px;font-weight:750}
    .source-mark{width:9px;height:9px;border-radius:50%;background:var(--orange);box-shadow:0 0 10px rgba(244,122,32,.25)}
    .source-mark.green{background:var(--green);box-shadow:0 0 10px rgba(112,222,137,.2)}
    .activity-copy{min-width:0}
    .activity-copy b{display:block;font-size:13px;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
    .activity-copy small{display:block;margin-top:4px;color:var(--muted);font-size:11px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
    .activity-tag{padding:6px 8px;border-radius:8px;background:var(--orange-soft);color:var(--orange);font:800 9px/1 ui-monospace,monospace;letter-spacing:.06em}
    .activity-tag.green{background:var(--green-soft);color:var(--green)}

    .rail-card{overflow:hidden}
    .rail-title{display:flex;align-items:center;justify-content:space-between;padding:14px 15px;border-bottom:1px solid var(--line);font-size:12px;font-weight:800;letter-spacing:.035em}
    .rail-title b{color:var(--orange);font:800 9px/1 ui-monospace,monospace;letter-spacing:.08em}
    .status-list,.detail-list{display:grid;padding:6px 0}
    .status-row,.detail-row{display:grid;grid-template-columns:1fr auto;align-items:center;gap:12px;padding:9px 15px;font-size:12px}
    .status-row span:first-child,.detail-row span:first-child{color:#b9c1c4}
    .status-value{display:flex;align-items:center;gap:7px;color:var(--green);font-weight:750}
    .mini-dot{width:7px;height:7px;border-radius:50%;background:currentColor;box-shadow:0 0 8px currentColor}
    .detail-row b{max-width:165px;color:#d9dedd;font-size:12px;text-align:right;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
    .detail-row b.orange{color:var(--orange)}
    .detail-row b.green{color:var(--green)}

    .brand-note{display:grid;grid-template-columns:58px 1fr;align-items:center;gap:12px;padding:12px 14px;border:1px solid rgba(244,122,32,.24);background:linear-gradient(135deg,rgba(244,122,32,.09),rgba(255,255,255,.015))}
    .brand-note img{width:58px;height:58px;object-fit:contain}
    .brand-note strong{display:block;color:var(--orange);font-size:12px;letter-spacing:.08em}
    .brand-note span{display:block;margin-top:4px;color:#afb8bc;font-size:11px;line-height:1.35}
    .principles{margin-top:7px;color:#8f999e;font:800 9px/1 ui-monospace,monospace;letter-spacing:.08em}
    .principles b{color:var(--orange)}

    footer{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:0 clamp(18px,2.4vw,40px);border-top:1px solid var(--line);background:#080c0e;color:var(--muted-2);font:750 9px/1 ui-monospace,monospace;letter-spacing:.08em;text-transform:uppercase}
    footer .secure{color:var(--green)}
    footer .secure:before{content:"●";margin-right:7px}
    footer b{color:var(--orange)}

    @keyframes pulse{from{transform:scaleY(.52);opacity:.42}to{transform:scaleY(1);opacity:.92}}
    @media(max-width:1100px){
      header{grid-template-columns:minmax(220px,1fr) auto}.top-nav{display:none}.workspace{grid-template-columns:minmax(0,1fr) 280px}.receiver{padding:19px}.receiver-state{min-width:215px}.activity-row{grid-template-columns:105px minmax(0,1fr) auto}.brand-copy small{display:none}
    }
    @media(max-width:820px){
      .app{grid-template-rows:68px minmax(0,1fr) 32px}.workspace{grid-template-columns:1fr;padding:12px 14px}.rail{display:none}.primary{grid-template-rows:minmax(0,1.2fr) minmax(200px,.8fr)}.brand img{width:48px;height:48px}.brand-copy strong{font-size:14px}.brand-copy b{font-size:12px}.receiver{padding:18px}.receiver-title h1{font-size:31px}.receiver-state{min-width:205px}.environment{display:none}
    }
    @media(max-width:640px){
      .app{grid-template-rows:60px minmax(0,1fr) 28px}.workspace{padding:8px}.brand img{width:42px;height:42px}.brand-copy strong{font-size:12px}.brand-copy b{font-size:10px}.system-pill{padding:8px 10px;font-size:9px}.receiver{padding:14px;gap:11px}.receiver-head{gap:12px}.receiver-title h1{font-size:25px}.receiver-title p{font-size:12px;margin-top:6px}.receiver-state{min-width:0;padding:10px 11px}.receiver-state strong{font-size:12px}.receiver-state span{font-size:10px}.receiver-meta{grid-template-columns:repeat(2,minmax(0,1fr));gap:6px}.meta{padding:8px 9px}.meta:nth-child(n+3){display:none}.activity{grid-template-rows:46px minmax(0,1fr)}.activity-head{padding:0 12px}.activity-head span{display:none}.activity-list{grid-template-rows:repeat(3,minmax(0,1fr))}.activity-row{grid-template-columns:86px minmax(0,1fr);gap:9px;padding:8px 12px}.activity-row:nth-child(4){display:none}.activity-tag{display:none}.activity-source{font-size:10px}.activity-copy b{font-size:11px}.activity-copy small{font-size:9px}.spectrum-foot{font-size:8px}.wave{gap:1px}.wave i{min-width:0}footer{font-size:7px}.footer-center{display:none}
    }
    @media(max-height:700px){
      .app{grid-template-rows:64px minmax(0,1fr) 28px}.workspace{padding-top:10px;padding-bottom:10px}.receiver{padding:16px;gap:10px}.receiver-title h1{font-size:28px}.receiver-title p{margin-top:5px;font-size:12px}.receiver-state{padding:9px 11px}.receiver-meta{gap:6px}.meta{padding:7px 9px}.activity{grid-template-rows:44px minmax(0,1fr)}.activity-row{padding-top:6px;padding-bottom:6px}.rail{gap:8px}.status-row,.detail-row{padding-top:6px;padding-bottom:6px}.brand-note{padding:8px 10px}.brand-note img{width:44px;height:44px}
    }
    @media(prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
  </style>
</head>
<body>
  <div class="app">
    <header>
      <a class="brand" href="https://www.terrasatch.com" aria-label="TerraSatch home">
        <img src="__BRAND_LOGO__" onerror="this.onerror=null;this.src='__BRAND_FALLBACK__'" alt="TerraSatch Sasquatch">
        <span class="brand-copy"><strong>TERRASATCH</strong><b>TERRALISTEN</b><small>Radio intelligence for field operations</small></span>
      </a>
      <nav class="top-nav" aria-label="API resources">
        <a class="top-link" href="/api/v1/reference">API Reference</a>
        __DOCS_NAV__
        <a class="top-link" href="/openapi.json">OpenAPI</a>
        <a class="top-link" href="/admin">Admin</a>
      </nav>
      <div class="header-state">
        <span class="environment">__ENVIRONMENT__</span>
        <span class="system-pill"><i class="dot"></i><span id="header-state">CHECKING SYSTEMS</span></span>
      </div>
    </header>

    <main class="workspace">
      <section class="primary">
        <section class="card receiver" aria-label="TerraListen receiver">
          <div class="receiver-head">
            <div class="receiver-title">
              <h1>TerraListen Receiver</h1>
              <p>Receive-only radio intelligence for field operations.</p>
            </div>
            <div class="receiver-state">
              <strong><i class="dot"></i><span id="receiver-state">CHECKING</span></strong>
              <span id="receiver-detail">Waiting for system readiness</span>
            </div>
          </div>

          <div class="spectrum" aria-label="Receiver visualization">
            <div class="spectrum-head"><span>Radio Receiver</span><span class="live-label"><i class="dot"></i>READY</span></div>
            <div class="wave" aria-hidden="true">__WAVE__</div>
            <div class="spectrum-foot"><span>AWAITING EDGE RECEIVER</span><span>NO ACTIVE SIGNAL</span></div>
          </div>

          <div class="receiver-meta">
            <div class="meta"><span>Mode</span><b class="green">Receive Only</b></div>
            <div class="meta"><span>Source</span><b>Edge / SDR</b></div>
            <div class="meta"><span>Channel</span><b class="orange">Waiting for input</b></div>
            <div class="meta"><span>Ingest</span><b class="green">Ready</b></div>
          </div>
        </section>

        <section class="card activity" aria-label="Live intelligence feed">
          <div class="activity-head"><strong>LIVE INTELLIGENCE</strong><span>Receiver → Transcript → TerraEngine → Event</span></div>
          <div class="activity-list">
            <div class="activity-row"><div class="activity-source"><i class="source-mark"></i>RECEIVER</div><div class="activity-copy"><b>Waiting for field receiver input</b><small>Nooelec / RTL-SDR edge capture will populate this stream.</small></div><span class="activity-tag">EDGE</span></div>
            <div class="activity-row"><div class="activity-source"><i class="source-mark green"></i>TERRAENGINE</div><div class="activity-copy"><b>Structured event pipeline ready</b><small>Transcripts can be converted into operational events.</small></div><span class="activity-tag green">READY</span></div>
            <div class="activity-row"><div class="activity-source"><i class="source-mark green"></i>INGEST API</div><div class="activity-copy"><b>/api/v1/transmissions</b><small>Authorized receive-side text ingestion endpoint.</small></div><span class="activity-tag green">ONLINE</span></div>
            <div class="activity-row"><div class="activity-source"><i class="source-mark green"></i>WEBSOCKET</div><div class="activity-copy"><b>/ws/v1/events</b><small>Tenant-authenticated realtime operational event stream.</small></div><span class="activity-tag green">READY</span></div>
          </div>
        </section>
      </section>

      <aside class="rail" aria-label="System and receiver status">
        <section class="card rail-card">
          <div class="rail-title"><span>SYSTEM STATUS</span><b>LIVE</b></div>
          <div class="status-list">
            <div class="status-row"><span>API</span><span class="status-value"><i class="mini-dot"></i><b id="api-state">CHECKING</b></span></div>
            <div class="status-row"><span>Database</span><span class="status-value"><i class="mini-dot"></i><b id="db-state">CHECKING</b></span></div>
            <div class="status-row"><span>Redis</span><span class="status-value"><i class="mini-dot"></i><b id="redis-state">CHECKING</b></span></div>
          </div>
        </section>

        <section class="card rail-card">
          <div class="rail-title"><span>RECEIVER STATUS</span><b>RX</b></div>
          <div class="detail-list">
            <div class="detail-row"><span>Mode</span><b class="green">Receive Only</b></div>
            <div class="detail-row"><span>Source</span><b>Edge / SDR</b></div>
            <div class="detail-row"><span>Channel</span><b class="orange">Waiting for input</b></div>
            <div class="detail-row"><span>Frequency</span><b>—</b></div>
            <div class="detail-row"><span>Transmission</span><b class="orange">Disabled</b></div>
          </div>
        </section>

        <section class="card rail-card">
          <div class="rail-title"><span>SYSTEM INFO</span><b>PROD</b></div>
          <div class="detail-list">
            <div class="detail-row"><span>Environment</span><b>__ENVIRONMENT__</b></div>
            <div class="detail-row"><span>Deployment</span><b>__DEPLOYMENT__</b></div>
            <div class="detail-row"><span>Version</span><b>v__VERSION__</b></div>
            <div class="detail-row"><span>Revision</span><b id="revision" class="mono">—</b></div>
            <div class="detail-row"><span>API</span><b>api.terrasatch.com</b></div>
          </div>
        </section>

        <section class="card brand-note">
          <img src="__BRAND_LOGO__" onerror="this.onerror=null;this.src='__BRAND_FALLBACK__'" alt="Sassy, TerraSatch Sasquatch">
          <div><strong>SASSY · TERRALISTEN</strong><span>Decision support for backcountry and remote field teams.</span><div class="principles"><b>LISTEN</b> · WATCH · LEARN · ADAPT</div></div>
        </section>
      </aside>
    </main>

    <footer>
      <span><b>TERRASATCH</b> · TERRAIN INTELLIGENCE</span>
      <span class="footer-center">NO AUTONOMOUS RADIO TRANSMISSIONS · DECISION SUPPORT ONLY</span>
      <span class="secure">SECURE API</span>
    </footer>
  </div>

  <script>
    (async()=>{
      const q=id=>document.getElementById(id);
      try{
        const r=await fetch('/health/ready',{cache:'no-store'});
        const p=await r.json();
        const healthy=r.ok&&p.status==='healthy';
        q('header-state').textContent=healthy?'SYSTEMS ONLINE':'SYSTEM DEGRADED';
        q('receiver-state').textContent=healthy?'RECEIVER READY':'SYSTEM DEGRADED';
        q('receiver-detail').textContent=healthy?'Waiting for field receiver input':'Check API readiness';
        q('api-state').textContent=healthy?'HEALTHY':'DEGRADED';
        q('revision').textContent=p.revision||'—';
        const deps=Object.fromEntries((p.dependencies||[]).map(d=>[d.name,d.status]));
        q('db-state').textContent=(deps.database||'unknown').toUpperCase();
        q('redis-state').textContent=(deps.redis||'unknown').toUpperCase();
      }catch(_){
        q('header-state').textContent='UNAVAILABLE';
        q('receiver-state').textContent='SYSTEM UNKNOWN';
        q('receiver-detail').textContent='Readiness request failed';
        q('api-state').textContent='UNKNOWN';
        q('db-state').textContent='UNKNOWN';
        q('redis-state').textContent='UNKNOWN';
      }
    })();
  </script>
</body>
</html>"""

    wave = "".join(
        f'<i style="--h:{height}%;--d:-{index * 0.06:.2f}s"></i>'
        for index, height in enumerate(
            (
                18,24,22,31,28,36,30,42,35,48,39,54,44,61,52,69,58,76,64,82,
                72,88,77,94,83,78,70,66,73,81,69,74,62,58,64,55,49,57,52,46,
                42,48,39,45,36,41,34,38,31,35,28,32,26,30,24,28,22,26,21,24,
                20,23,18,21,17,20,16,19,17,18,16,20,18,23,19,25,21,28,23,31,
                26,34,29,37,32,40,35,43,37,46,39,49,41,52,44,55,47,58,50,61,
                52,56,48,51,44,47,40,43,37,40,34,38,31,35,29,33,27,31,25,29,
            )
        )
    )
    replacements["__WAVE__"] = wave
    for marker, value in replacements.items():
        html = html.replace(marker, value)
    return html
