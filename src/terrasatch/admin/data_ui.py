"""Server-rendered control-plane data source and inspector screens."""
# ruff: noqa: E501

from __future__ import annotations

from html import escape

from terrasatch.brand import SASQUATCH_ASSET_URL
from terrasatch.masterdata.service import InspectorResult


def _attr(value: object) -> str:
    return escape(str(value), quote=True)


def _layout(title: str, body: str) -> str:
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(title)} · TerraSatch</title>{_styles()}</head><body><aside><a class="brand" href="/admin"><img src="{escape(SASQUATCH_ASSET_URL)}" alt=""><span><strong>TERRASATCH</strong><b>CONTROL PLANE</b></span></a><nav><a href="/admin">Operations</a><a href="/admin/data-sources">Data sources</a><a href="/admin/data-inspector">Data inspector</a><a href="/admin/members">Members & access</a></nav><small>LISTEN · WATCH · LEARN · ADAPT</small></aside><main>{body}</main></body></html>'''


def _organization_select(organizations: list[object], selected: str, path: str) -> str:
    options = ["<option value=''>Select organization</option>"]
    for item in organizations:
        is_selected = " selected" if str(item.id) == selected else ""
        options.append(
            f"<option value='{_attr(item.id)}'{is_selected}>{escape(str(item.name))}</option>"
        )
    return f"<form class='context' method='get' action='{path}'><label>Organization<select name='organization' onchange='this.form.submit()'>{''.join(options)}</select></label></form>"


def render_data_sources(
    *,
    organizations: list[object],
    selected_organization: str,
    selected_name: str,
    sources: list[object],
    record_counts: dict[object, int],
    sync_runs: list[object],
    backups: list[object],
    csrf_token: str,
    error_message: str | None,
) -> str:
    source_rows = []
    for source in sources:
        source_rows.append(
            f"<tr><td><strong>{escape(str(source.name))}</strong><small>{escape(str(source.provider))} · {escape(str(source.source_kind))}</small></td><td><code>{escape(str(source.adapter_key))}@{escape(str(source.adapter_version or '—'))}</code></td><td><span class='status {escape(str(source.status))}'>{escape(str(source.status)).upper()}</span></td><td>{escape(str(source.last_successful_sync or 'never'))}</td><td>{record_counts.get(source.id, 0)}</td><td><form method='post' action='/admin/data-sources/{_attr(source.id)}/sync'><input type='hidden' name='organization' value='{_attr(selected_organization)}'><input type='hidden' name='csrf_token' value='{_attr(csrf_token)}'><button {'disabled' if not source.enabled else ''}>Queue sync</button></form></td></tr>"
        )
    if not source_rows:
        source_rows.append(
            "<tr><td colspan='6' class='empty'>No data sources configured for this organization.</td></tr>"
        )

    run_rows = []
    for run in sync_runs:
        run_rows.append(
            f"<tr><td><code>{escape(str(run.id))}</code></td><td>{escape(str(run.data_source_id))}</td><td><span class='status {escape(str(run.status))}'>{escape(str(run.status)).upper()}</span></td><td>{escape(str(run.created_at))}</td><td>{run.fetched_count} / {run.created_count} / {run.updated_count} / {run.unchanged_count} / {run.rejected_count}</td><td>{escape(str(run.runtime_ms or '—'))}</td></tr>"
        )
    if not run_rows:
        run_rows.append("<tr><td colspan='6' class='empty'>No sync jobs recorded.</td></tr>")

    backup_rows = []
    for item in backups:
        backup_rows.append(
            f"<tr><td>{escape(str(item.backup_type))}</td><td>{escape(str(item.provider))}</td><td><span class='status {escape(str(item.status))}'>{escape(str(item.status)).upper()}</span></td><td>{escape(str(item.started_at))}</td><td>{escape(str(item.restore_test_status))}</td><td>{escape(str(item.retention_until or '—'))}</td></tr>"
        )
    if not backup_rows:
        backup_rows.append(
            "<tr><td colspan='6' class='empty'>No backup system has reported state yet. Backup execution remains outside the browser.</td></tr>"
        )

    alert = f"<div class='alert'>{escape(error_message)}</div>" if error_message else ""
    selected_heading = escape(selected_name or "Select an organization")
    create_panel = ""
    if selected_organization:
        create_panel = f'''<section><div class="head"><div><small>// REGISTER SOURCE</small><h2>Add a disabled-by-default adapter</h2></div></div><form class="grid" method="post" action="/admin/data-sources"><input type="hidden" name="organization" value="{_attr(selected_organization)}"><input type="hidden" name="csrf_token" value="{_attr(csrf_token)}"><label>Name<input name="name" placeholder="Utah Avalanche Center" required></label><label>Provider<input name="provider" placeholder="uac" required></label><label>Source kind<input name="source_kind" placeholder="avalanche_observations" required></label><label>Adapter<select name="adapter_key"><option value="manual_snapshot">manual_snapshot</option></select></label><label>Endpoint URL<input name="endpoint_url" placeholder="https://provider.example/api"></label><label>Credential reference<input name="credential_reference" placeholder="oci-vault://... (never a raw token)"></label><label class="check"><input type="checkbox" name="enabled" value="true"> Enable immediately</label><button>Create source</button></form></section>'''

    body = f"""<header><div><small>MASTER OPERATIONAL INDEX</small><h1>{selected_heading} data plane</h1><p>Provider syncs are queued only. Edge ingestion, TerraEngine, Redis realtime, and current event contracts stay untouched.</p></div>{_organization_select(organizations, selected_organization, "/admin/data-sources")}</header>{alert}<section><div class="head"><div><small>// DATA SOURCES</small><h2>Connections and normalized records</h2></div><a href="/admin/data-inspector?organization={_attr(selected_organization)}">Open inspector</a></div><div class="table"><table><thead><tr><th>Source</th><th>Adapter</th><th>Status</th><th>Last success</th><th>Records</th><th>Action</th></tr></thead><tbody>{"".join(source_rows)}</tbody></table></div></section>{create_panel}<section><div class="head"><div><small>// SYNC HISTORY</small><h2>Bounded background jobs</h2></div></div><div class="table"><table><thead><tr><th>Run</th><th>Source</th><th>Status</th><th>Queued</th><th>Fetched / Created / Updated / Same / Rejected</th><th>ms</th></tr></thead><tbody>{"".join(run_rows)}</tbody></table></div></section><section><div class="head"><div><small>// BACKUP VISIBILITY</small><h2>Recovery evidence</h2></div></div><div class="table"><table><thead><tr><th>Type</th><th>Provider</th><th>Status</th><th>Started</th><th>Restore test</th><th>Retention</th></tr></thead><tbody>{"".join(backup_rows)}</tbody></table></div></section>"""
    return _layout("Data Sources", body)


def render_data_inspector(
    *,
    organizations: list[object],
    selected_organization: str,
    selected_name: str,
    query: str,
    results: list[InspectorResult],
    error_message: str | None,
) -> str:
    cards = []
    for item in results:
        details = "".join(
            f"<dt>{escape(str(key))}</dt><dd>{escape(str(value))}</dd>"
            for key, value in item.details.items()
        )
        cards.append(
            f"<article><div class='type'>{escape(item.record_type)}</div><h2>{escape(item.title)}</h2><code>{escape(str(item.record_id))}</code><p>{escape(item.subtitle)}</p><dl><dt>Provenance</dt><dd>{escape(item.provenance or 'n/a')}</dd><dt>Spatial</dt><dd>{escape(item.spatial or 'n/a')}</dd>{details}</dl></article>"
        )
    if query and not cards:
        cards.append(
            "<div class='empty card'>No canonical or source records matched this query.</div>"
        )
    alert = f"<div class='alert'>{escape(error_message)}</div>" if error_message else ""
    body = f'''<header><div><small>CANONICAL DATA INSPECTOR</small><h1>{escape(selected_name or "Select an organization")}</h1><p>Search exact UUIDs, provider IDs, callsigns, locations, transcripts, regions, and stable terrain cell IDs.</p></div>{_organization_select(organizations, selected_organization, "/admin/data-inspector")}</header>{alert}<section><form class="search" method="get" action="/admin/data-inspector"><input type="hidden" name="organization" value="{_attr(selected_organization)}"><input name="q" value="{_attr(query)}" placeholder="Event UUID, Cardiff Bowl, Patrol 4, TS-UT-SLC-004813..." required><button>Inspect</button></form></section><div class="cards">{"".join(cards)}</div>'''
    return _layout("Data Inspector", body)


def _styles() -> str:
    return """<style>:root{--bg:#080a0c;--panel:#0d1013;--line:#252a30;--text:#eef1f4;--muted:#8b949e;--orange:#ff8a00;--green:#6ee7a0;--red:#ff7777}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:13px ui-monospace,SFMono-Regular,Consolas,monospace;display:grid;grid-template-columns:230px 1fr;min-height:100vh}aside{border-right:1px solid var(--line);padding:22px 18px;display:flex;flex-direction:column;gap:28px}.brand{display:flex;gap:10px;align-items:center;color:inherit;text-decoration:none}.brand img{width:42px;height:42px;object-fit:contain}.brand span{display:grid}.brand strong{letter-spacing:.14em}.brand b{font-size:9px;color:var(--orange)}nav{display:grid;gap:5px}nav a{padding:9px;color:var(--muted);text-decoration:none;border-left:2px solid transparent}nav a:hover{color:var(--orange);border-color:var(--orange)}aside>small{margin-top:auto;color:#5d6670}main{padding:28px;min-width:0;max-width:1500px;width:100%}header{display:flex;justify-content:space-between;gap:20px;align-items:end;margin-bottom:18px}h1{font-size:24px;margin:3px 0 8px}h2{font-size:15px;margin:3px 0}p{color:var(--muted);margin:0;max-width:760px;line-height:1.55}header small,.head small,.type{color:var(--orange);font-size:9px;letter-spacing:.13em}section,article{background:var(--panel);border:1px solid var(--line);border-radius:8px;margin-bottom:14px}.head{padding:14px 16px;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;align-items:center}.head a{color:var(--orange)}.context{min-width:260px}label{display:grid;gap:6px;color:var(--muted);font-size:10px}input,select{border:1px solid var(--line);background:#080a0c;color:var(--text);padding:10px;border-radius:4px;font:inherit;width:100%}button{border:1px solid var(--orange);background:var(--orange);color:#211100;padding:8px 10px;border-radius:4px;font:800 10px inherit;cursor:pointer}button:disabled{opacity:.35;cursor:not-allowed}.grid{padding:16px;display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.grid button{align-self:end;height:38px}.check{display:flex;align-items:center;gap:8px}.check input{width:auto}.table{overflow:auto}table{border-collapse:collapse;width:100%;min-width:900px}th,td{text-align:left;padding:10px 13px;border-top:1px solid #1d2228;vertical-align:top}thead th{border-top:0;color:#68727d;font-size:9px;text-transform:uppercase}td small{display:block;color:var(--muted);margin-top:4px}.status{color:var(--orange)}.status.connected,.status.ready,.status.succeeded,.status.healthy{color:var(--green)}.status.failed,.status.error{color:var(--red)}.empty{color:var(--muted);padding:20px}.alert{border:1px solid rgba(255,119,119,.35);color:#ff9a9a;padding:12px;margin-bottom:14px;border-radius:5px}.search{padding:14px;display:grid;grid-template-columns:1fr auto;gap:10px}.cards{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.cards article{padding:16px;margin:0}.cards article h2{font-size:14px;margin:7px 0}.cards article>code{color:var(--orange);font-size:10px}.cards article p{margin:9px 0}.cards dl{display:grid;grid-template-columns:92px 1fr;gap:7px 10px;margin:14px 0 0;font-size:10px}.cards dt{color:#68727d}.cards dd{margin:0;overflow-wrap:anywhere}.card{border:1px solid var(--line);border-radius:8px}@media(max-width:950px){body{grid-template-columns:1fr}aside{border-right:0;border-bottom:1px solid var(--line);position:relative}nav{display:flex;flex-wrap:wrap}aside>small{display:none}header{align-items:start;flex-direction:column}.context{width:100%}.grid{grid-template-columns:1fr}.cards{grid-template-columns:1fr}}</style>"""
