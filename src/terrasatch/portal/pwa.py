# ruff: noqa: E501
"""Public PWA shell assets; authenticated workspace data is never cached offline."""

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse, Response

router = APIRouter()
ASSET_DIRECTORY = Path(__file__).parents[1] / "static" / "workspace"
OFFLINE = """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#080b0d"><title>TerraSatch · Offline</title><body style="margin:0;background:#080b0d;color:#edf1f0;font:16px system-ui;display:grid;min-height:100vh;place-items:center"><main style="max-width:420px;padding:24px"><h1>You're offline</h1><p>Reconnect to open your TerraSatch workspace. Email, account details, and organization data are not stored for offline access.</p><a style="color:#ffbd45" href="/portal">Try again</a></main></body></html>"""
WORKER = r"""
const CACHE='terrasatch-workspace-public-v1';
const PUBLIC=['/portal/offline','/workspace-assets/icon.svg'];
self.addEventListener('install',e=>e.waitUntil(caches.open(CACHE).then(c=>c.addAll(PUBLIC))));
self.addEventListener('activate',e=>e.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k.startsWith('terrasatch-workspace-public-')&&k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim())));
self.addEventListener('fetch',e=>{
 const u=new URL(e.request.url);
 if(e.request.method!=='GET'||u.origin!==self.location.origin)return;
 if(e.request.mode==='navigate'&&(u.pathname==='/portal'||u.pathname.startsWith('/portal/'))){
   e.respondWith(fetch(e.request).catch(()=>caches.match('/portal/offline')));return;
 }
 if(PUBLIC.includes(u.pathname)&&!u.search)e.respondWith(caches.match(e.request).then(r=>r||fetch(e.request)));
});
"""


@router.get("/portal/manifest.webmanifest", include_in_schema=False)
async def manifest():
    return JSONResponse(
        {
            "id": "/portal",
            "name": "TerraSatch Workspace",
            "short_name": "TerraSatch",
            "description": "Your team, email, connected tools, and Satchy in one workspace.",
            "start_url": "/portal",
            "scope": "/portal",
            "display": "standalone",
            "background_color": "#080b0d",
            "theme_color": "#080b0d",
            "icons": [
                {
                    "src": "/workspace-assets/icon.svg",
                    "sizes": "any",
                    "type": "image/svg+xml",
                    "purpose": "any maskable",
                }
            ],
            "shortcuts": [
                {"name": "Email", "url": "/portal#email"},
                {"name": "Tools & services", "url": "/portal#services"},
            ],
        },
        media_type="application/manifest+json",
    )


@router.get("/portal/service-worker.js", include_in_schema=False)
async def service_worker():
    return Response(
        WORKER,
        media_type="text/javascript",
        headers={
            "Cache-Control": "no-cache",
            "Service-Worker-Allowed": "/portal",
        },
    )


@router.get("/portal/offline", include_in_schema=False)
async def offline():
    return HTMLResponse(OFFLINE, headers={"Cache-Control": "public, max-age=3600"})
