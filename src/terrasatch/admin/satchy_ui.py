"""Satchy review workspace using the shared admin console theme."""
# ruff: noqa: E501

from __future__ import annotations

from collections.abc import Sequence
from html import escape
from typing import Any
from urllib.parse import urlencode

from terrasatch.admin.ui import _styles as admin_styles
from terrasatch.brand import SATCHY_ASSET_URL


def _value(item: object | None, name: str, default: object = None) -> object:
    return getattr(item, name, default) if item is not None else default


def _stage(status: str, target: str) -> str:
    # A physical TX status must never be displayed as a successful simulation.
    order = {
        "queued": 1,
        "dispatched": 1,
        "edge_received": 2,
        "waiting_channel_clear": 2,
        "transmitting": 2,
        "transmitted": 2,
        "simulated": 3,
    }
    return "done" if order.get(status, 0) >= order[target] else "pending"


def _status_tone(status: str) -> str:
    if status in {"failed", "rejected", "expired", "cancelled"}:
        return "attention"
    if status in {"completed", "simulated"}:
        return "complete"
    return "review"


def render_satchy_control_plane(
    *,
    organizations: Sequence[object],
    selected_organization: str,
    selected_name: str,
    workflows: list[dict[str, Any]],
    csrf_token: str,
    error_message: str | None = None,
) -> str:
    options = [
        f'<option value="{escape(str(_value(org, "id")))}" '
        f"{'selected' if str(_value(org, 'id')) == selected_organization else ''}>"
        f"{escape(str(_value(org, 'name', 'Organization')))}</option>"
        for org in organizations
    ]
    context = f"?{urlencode({'organization': selected_organization})}" if selected_organization else ""
    admin_url = escape(f"/admin{context}")
    hidden_fields = (
        f'<input type="hidden" name="csrf_token" value="{escape(csrf_token)}">'
        f'<input type="hidden" name="organization" value="{escape(selected_organization)}">'
    )
    cards: list[str] = []
    for workflow in workflows:
        action = workflow["action"]
        evaluation = workflow.get("evaluation")
        transmission = workflow.get("transmission")
        transcript = workflow.get("transcript")
        conversation = workflow.get("conversation")
        outbound = workflow.get("outbound")
        command = workflow.get("command")
        action_id = escape(str(_value(action, "id")))
        action_status = str(_value(action, "status", "unknown"))
        action_type = str(_value(action, "action_type", "review"))
        outbound_status = str(_value(outbound, "status", "not queued"))
        raw_participants = _value(conversation, "participants", [])
        participants = (
            [str(item) for item in raw_participants]
            if isinstance(raw_participants, list)
            else ["Unresolved"]
        )
        raw_confidence = _value(evaluation, "confidence", 0)
        confidence = float(raw_confidence) if isinstance(raw_confidence, (int, float, str)) else 0.0
        controls = ""
        if action_status == "awaiting_approval":
            message = escape(str(_value(action, "proposed_message", "") or ""))
            controls = f"""
            <div class="satchy-review">
              <form method="post" action="/admin/satchy/actions/{action_id}/approve" class="review-form">
                {hidden_fields}
                <label>Edit proposed response<textarea name="message" rows="3">{message}</textarea></label>
                <label>Approval notes<input name="notes" maxlength="1000" placeholder="Optional review notes"></label>
                <button class="approve" type="submit">Approve</button>
              </form>
              <div class="review-footer"><p class="subtle">Human approval is required. Radio replies are queued for simulation.</p>
                <form method="post" action="/admin/satchy/actions/{action_id}/reject" class="reject-form">
                  {hidden_fields}
                  <input type="hidden" name="notes" value="Rejected from Satchy control plane">
                  <button class="reject" type="submit">Reject</button>
                </form>
              </div>
            </div>
            """
        simulated_label = "Simulated ✓" if outbound_status == "simulated" else "Simulated"
        cards.append(
            f"""
            <article class="workflow terminal-window" aria-labelledby="action-{action_id}">
              <div class="terminal-chrome"><span></span><span></span><span></span><b>transmission → review → Edge</b></div>
              <div class="workflow-heading"><h2 id="action-{action_id}">{escape(action_type.replace('_', ' ').title())}</h2>
                <span class="satchy-status {_status_tone(action_status)}">{escape(action_status.replace('_', ' ').title())}</span></div>
              <div class="satchy-grid">
                <section><h3>01 / Incoming</h3><blockquote>{escape(str(_value(transcript, "raw_text", "Transcript unavailable")))}</blockquote>
                  <p class="subtle">Source preserved · {escape(str(_value(transmission, "source_type", "unknown")))}</p></section>
                <section><h3>02 / Conversation</h3><p class="participants">{escape(" ↔ ".join(participants or ["Unresolved"]))}</p>
                  <p class="subtle">{escape(str(_value(conversation, "primary_topic", "Operational radio")))}</p></section>
                <section><h3>03 / Satchy proposal</h3><blockquote>{escape(str(_value(action, "proposed_message", "Human emergency review required") or "Human emergency review required"))}</blockquote>
                  <p class="subtle">Confidence <strong class="confidence">{confidence:.0%}</strong> · {escape(str(_value(evaluation, "interpretation", "")))}</p></section>
              </div>
              {controls}
              <div class="satchy-delivery"><div class="delivery-heading"><h3>Outbound lifecycle</h3><span class="satchy-status {_status_tone(outbound_status)}">{escape(outbound_status.replace('_', ' ').title())}</span></div>
                <ol class="lifecycle" aria-label="Outbound lifecycle">
                  <li class="{_stage(outbound_status, 'queued')}"><span class="stage-number">01</span>Queued</li>
                  <li class="{_stage(outbound_status, 'edge_received')}"><span class="stage-number">02</span>Edge received</li>
                  <li class="{_stage(outbound_status, 'simulated')}"><span class="stage-number">03</span>{simulated_label}</li>
                </ol>
                <dl class="workflow-ids"><div><dt>Action</dt><dd>{action_id}</dd></div><div><dt>Edge command</dt><dd>{escape(str(_value(command, 'id', 'not created')))}</dd></div></dl>
              </div>
            </article>
            """
        )
    empty = ""
    if not cards:
        empty_title = "No Satchy proposals yet" if selected_organization else "Select an organization"
        empty_detail = (
            "Ingest “Satchy, Control 2.” through the normal receive path to begin."
            if selected_organization
            else "Choose an organization above and select Inspect to review its Satchy proposals."
        )
        empty = f'<section class="console-section satchy-empty"><h2>{empty_title}</h2><p class="subtle">{empty_detail}</p></section>'
    error = f'<div class="terminal-alert error" role="alert">{escape(error_message)}</div>' if error_message else ""
    return f"""<!doctype html>
    <html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <meta name="theme-color" content="#08090b"><title>Satchy action control plane · TerraSatch</title>
    <link rel="icon" type="image/png" href="{escape(SATCHY_ASSET_URL)}">
    {admin_styles()}{_satchy_styles()}</head><body class="satchy-page"><div class="admin-shell">
    <aside class="sidebar"><a class="brand" href="{admin_url}"><img src="{escape(SATCHY_ASSET_URL)}" alt=""><span><strong>TERRASATCH</strong><small>ADMIN CONSOLE</small></span></a>
      <nav aria-label="Admin console"><span>CONSOLE</span><a href="{admin_url}">‹ Operations console</a>
        <span>TENANT</span><a href="{admin_url}#tenant">› Organizations</a><a href="{admin_url}#sites">› Sites</a>
        <span>EDGE</span><a href="{admin_url}#radio">› Radio capability</a><a href="/admin/edge/pair{escape(context)}">› Pairings</a><a href="{admin_url}#fleet">› Registered Edge health</a>
        <a href="/admin/satchy{escape(context)}" aria-current="page">› Satchy control plane</a><a href="/admin/data-sources{escape(context)}">› Data sources</a><a href="/admin/data-inspector{escape(context)}">› Data inspector</a>
        <span>ACCESS</span><a href="/admin/members{escape(context)}">› Members &amp; access</a><a href="{admin_url}#keys">› API keys</a>
        <span>SYSTEM</span><a href="{admin_url}#system">› Components</a><a href="{admin_url}#reference">› API reference</a><a href="/docs">› OpenAPI docs</a></nav>
      <div class="sidebar-foot"><small>SIMULATION-ONLY CONTROL</small><p>AI proposes. An operator approves. Edge reports the simulated result.</p>
        <form method="post" action="/admin/logout"><input type="hidden" name="csrf_token" value="{escape(csrf_token)}"><button class="button-ghost" type="submit">logout</button></form></div>
    </aside>
    <main class="workspace"><header class="workspace-header"><div><p class="shell-path">ts-admin@terrasatch:<span>~</span>$ satchy review</p><h1>Satchy action control plane</h1></div><div class="connection">OPERATOR REVIEW</div></header>
      {error}
      <section class="capability-strip" aria-label="Control plane safety"><div><small>RECEIVE PATH</small><strong>RX PILOT UNCHANGED</strong><p>Incoming radio and source transcripts remain preserved.</p></div><div><small>APPROVAL</small><strong>HUMAN IN THE LOOP</strong><p>Satchy proposes actions; an operator authorizes them.</p></div><div><small>OUTBOUND</small><strong>SIMULATION ONLY</strong><p>No physical RF or PTT transmission in this release.</p></div></section>
      <section class="console-section satchy-context"><div><small>// ORGANIZATION</small><h2>{escape(selected_name)}</h2><p class="subtle">Review proposals and their outbound delivery status.</p></div>
        <form method="get" action="/admin/satchy"><div class="context-field"><label for="satchy-organization">Organization</label><select id="satchy-organization" name="organization"><option value="">Select organization</option>{''.join(options)}</select></div><button type="submit">Inspect</button></form></section>
      {''.join(cards)}{empty}
      <footer>TerraSatch <span>•</span> LISTEN · WATCH · LEARN · ADAPT <span>•</span> Operator-controlled actions</footer>
    </main></div></body></html>"""


def _satchy_styles() -> str:
    """Only page-specific layout; colors and shared components come from admin.ui."""
    return """<style>
    .satchy-page{color-scheme:dark}
    .satchy-page :is(a,button,textarea,input,select):focus-visible{outline:2px solid var(--accent2);outline-offset:3px}
    .satchy-page nav a[aria-current=page]{background:var(--accent-soft);color:var(--accent2);border-left:2px solid var(--accent)}
    .satchy-page .workspace-header{gap:16px;flex-wrap:wrap}
    .satchy-page h1{font-size:clamp(18px,2vw,24px)}
    .satchy-page .satchy-context{display:flex;justify-content:space-between;align-items:center;gap:24px;padding:18px}
    .satchy-context small{color:var(--accent);font-size:9px;letter-spacing:.14em}
    .satchy-context h2{margin:4px 0}.satchy-context p{margin:0;font-size:11px}
    .satchy-context form{display:flex;align-items:end;gap:10px;max-width:100%;min-width:300px}
    .satchy-context .context-field{flex:1;min-width:0}.satchy-context label{margin:0}.satchy-context select{min-height:38px}
    .satchy-page button{min-height:38px}
    .satchy-page .workflow{margin:18px 0}
    .workflow-heading{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:16px 18px;flex-wrap:wrap}
    .workflow-heading h2{font-size:14px}
    .satchy-status{display:inline-block;border:1px solid var(--line2);border-radius:4px;padding:4px 8px;font:10px var(--mono);color:var(--muted)}
    .satchy-status.review{color:var(--accent2);border-color:var(--accent);background:var(--accent-soft)}
    .satchy-status.complete{color:var(--text);border-color:var(--accent);background:var(--accent-soft)}
    .satchy-status.attention{color:#ff9b9b;border-color:var(--danger);background:var(--danger-soft)}
    .satchy-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:22px;padding:4px 18px 18px}
    .satchy-grid section{min-width:0;overflow-wrap:anywhere}.satchy-grid h3{font-size:10px;margin:0 0 12px}
    .satchy-grid blockquote{margin:0 0 12px;padding:12px 14px;background:var(--panel2);border-left:2px solid var(--accent);line-height:1.7}
    .satchy-grid p{font-size:11px;margin:0}.satchy-grid .participants{font-size:16px;margin:0 0 12px;line-height:1.6}
    .confidence{color:var(--accent2)}
    .satchy-review{border-top:1px solid var(--line);padding:18px}
    .review-form{display:grid;grid-template-columns:minmax(0,2fr) minmax(0,1fr) auto;gap:12px;align-items:end}
    .review-form label{margin:0;min-width:0}
    .review-form textarea{display:block;width:100%;min-height:76px;resize:vertical;margin-top:5px;border:1px solid var(--line2);border-radius:4px;background:#090b0d;color:var(--text);padding:10px;font:12px/1.6 var(--mono)}
    .review-footer{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-top:12px}
    .review-footer p{font-size:10px;margin:0}
    .satchy-page .reject{border-color:var(--danger);background:var(--danger-soft);color:#ff9b9b}
    .satchy-page .approve:hover{background:var(--accent2)}.satchy-page .reject:hover{background:var(--danger);color:var(--bg)}
    .satchy-delivery{border-top:1px solid var(--line);padding:16px 18px;background:var(--panel)}
    .delivery-heading{display:flex;align-items:center;justify-content:space-between;gap:12px}.delivery-heading h3{margin:0;font-size:10px}
    .lifecycle{list-style:none;padding:0;margin:14px 0;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}
    .lifecycle li{display:flex;align-items:center;gap:8px;border:1px solid var(--line);border-radius:4px;padding:10px;color:var(--muted);font-size:11px}
    .stage-number{display:inline-grid;place-items:center;width:23px;height:23px;flex-shrink:0;border:1px solid var(--line2);border-radius:50%;font-size:9px}
    .lifecycle .done{color:var(--accent2);border-color:var(--accent);background:var(--accent-soft)}.done .stage-number{border-color:var(--accent)}
    .workflow-ids{display:flex;flex-wrap:wrap;gap:8px 24px;margin:0;color:var(--muted);font:9px/1.6 var(--mono)}
    .workflow-ids div{min-width:0}.workflow-ids dt{display:inline;margin-right:8px}.workflow-ids dd{display:inline;margin:0;overflow-wrap:anywhere}
    .satchy-empty{padding:32px 18px;text-align:center}.satchy-empty h2{margin-bottom:8px}.satchy-empty p{margin:0}
    @media(max-width:1200px){.satchy-grid{gap:16px}.review-form{grid-template-columns:minmax(0,2fr) minmax(0,1fr)}.review-form .approve{grid-column:1/-1;justify-self:start}}
    @media(max-width:1050px){.satchy-page .sidebar nav{padding-bottom:0}.satchy-page .sidebar nav span{display:none}.satchy-page .sidebar .brand{padding-bottom:12px}.satchy-page .capability-strip{grid-template-columns:repeat(3,minmax(0,1fr))}.satchy-page .capability-strip>div{border-bottom:0;border-right:1px solid var(--line)}}
    @media(max-width:760px){.satchy-page .satchy-context{align-items:stretch;flex-direction:column;gap:16px}.satchy-context form{min-width:0}.satchy-grid{grid-template-columns:1fr}.satchy-grid section+section{padding-top:16px;border-top:1px solid var(--line)}.review-form{grid-template-columns:1fr}.review-form .approve{justify-self:stretch}.review-footer{align-items:flex-start}.satchy-page .capability-strip{display:block}.satchy-page .capability-strip>div{border-right:0;border-bottom:1px solid var(--line)}.lifecycle{grid-template-columns:1fr}.workflow-ids{flex-direction:column}.satchy-page nav a{min-height:36px;display:flex;align-items:center}}
    </style>"""
