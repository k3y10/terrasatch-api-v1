"""Small operational Satchy action inspection page."""
# ruff: noqa: E501

from __future__ import annotations

from collections.abc import Sequence
from html import escape
from typing import Any


def _value(item: object | None, name: str, default: object = None) -> object:
    return getattr(item, name, default) if item is not None else default


def _stage(status: str, target: str) -> str:
    order = {
        "queued": 1,
        "dispatched": 1,
        "edge_received": 2,
        "simulated": 3,
        "transmitting": 3,
        "transmitted": 3,
    }
    active = order.get(status, 0) >= order[target]
    return "done" if active else "pending"


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
        status = str(_value(outbound, "status", "not queued"))
        raw_participants = _value(conversation, "participants", [])
        participants = (
            [str(item) for item in raw_participants]
            if isinstance(raw_participants, list)
            else ["Unresolved"]
        )
        raw_confidence = _value(evaluation, "confidence", 0)
        confidence = float(raw_confidence) if isinstance(raw_confidence, (int, float, str)) else 0.0
        controls = ""
        if str(_value(action, "status")) == "awaiting_approval":
            message = escape(str(_value(action, "proposed_message", "") or ""))
            controls = f"""
            <form method="post" action="/admin/satchy/actions/{action_id}/approve" class="review-form">
              <input type="hidden" name="csrf_token" value="{escape(csrf_token)}">
              <input type="hidden" name="organization" value="{escape(selected_organization)}">
              <label>Edit proposed response<textarea name="message">{message}</textarea></label>
              <label>Approval notes<input name="notes" maxlength="1000"></label>
              <button class="approve" type="submit">Approve</button>
            </form>
            <form method="post" action="/admin/satchy/actions/{action_id}/reject" class="reject-form">
              <input type="hidden" name="csrf_token" value="{escape(csrf_token)}">
              <input type="hidden" name="organization" value="{escape(selected_organization)}">
              <input type="hidden" name="notes" value="Rejected from Satchy control plane">
              <button class="reject" type="submit">Reject</button>
            </form>
            """
        cards.append(
            f"""
            <article class="workflow">
              <div class="topline"><span class="badge">{escape(str(_value(action, "action_type")))}</span>
                <strong>{escape(str(_value(action, "status"))).replace("_", " ").title()}</strong></div>
              <div class="grid">
                <section><h2>Incoming</h2><blockquote>{escape(str(_value(transcript, "raw_text", "Transcript unavailable")))}</blockquote>
                  <p>Source preserved · {escape(str(_value(transmission, "source_type", "unknown")))}</p></section>
                <section><h2>Conversation</h2><p class="large">{escape(" ↔ ".join(participants or ["Unresolved"]))}</p>
                  <p>{escape(str(_value(conversation, "primary_topic", "Operational radio")))}</p></section>
                <section><h2>Satchy proposal</h2><blockquote>{escape(str(_value(action, "proposed_message", "Human emergency review required") or "Human emergency review required"))}</blockquote>
                  <p>Confidence <strong>{confidence:.0%}</strong> · {escape(str(_value(evaluation, "interpretation", "")))}</p></section>
              </div>
              {controls}
              <div class="lifecycle" aria-label="Outbound lifecycle">
                <span class="{_stage(status, "queued")}">Queued</span><i>→</i>
                <span class="{_stage(status, "edge_received")}">Edge received</span><i>→</i>
                <span class="{_stage(status, "simulated")}">Simulated ✓</span>
              </div>
              <p class="ids">Action {action_id} · Edge command {escape(str(_value(command, "id", "not created")))}</p>
            </article>
            """
        )
    empty = (
        '<div class="empty">No Satchy proposals yet. Ingest “Satchy, Control 2.” '
        "through the normal receive path to begin.</div>"
        if selected_organization and not cards
        else ""
    )
    error = f'<div class="error">{escape(error_message)}</div>' if error_message else ""
    return f"""<!doctype html>
    <html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>Satchy action control plane · TerraSatch</title>
    <style>
    :root{{--ink:#18231f;--muted:#64706b;--line:#dce3df;--paper:#f5f7f4;--green:#0f6b4c;--orange:#db6a27}}
    *{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:15px/1.5 system-ui,sans-serif}}
    header{{background:#101b17;color:white;padding:22px 5vw;display:flex;align-items:center;justify-content:space-between}}
    header a{{color:#bfe6d6;text-decoration:none}}main{{max-width:1200px;margin:auto;padding:32px 5vw 70px}}
    .toolbar{{display:flex;gap:15px;align-items:end;justify-content:space-between;margin:16px 0 28px}}select{{padding:10px;min-width:270px}}
    .workflow{{background:white;border:1px solid var(--line);border-radius:14px;padding:22px;margin:18px 0;box-shadow:0 8px 24px #193a2b0b}}
    .topline{{display:flex;justify-content:space-between}}.badge{{background:#e3f1eb;color:var(--green);padding:4px 9px;border-radius:99px}}
    .grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:18px;margin:18px 0}}h1{{margin:0}}h2{{font-size:12px;text-transform:uppercase;letter-spacing:.12em;color:var(--muted)}}
    blockquote{{margin:0;padding:13px 15px;border-left:3px solid var(--orange);background:#fafbfa}}.large{{font-size:20px}}
    .review-form{{display:grid;grid-template-columns:2fr 1fr auto;gap:12px;align-items:end;border-top:1px solid var(--line);padding-top:18px}}
    label{{font-size:12px;color:var(--muted)}}textarea,input{{display:block;width:100%;padding:9px;margin-top:5px;border:1px solid #bdc9c3;border-radius:6px}}
    textarea{{min-height:62px}}button{{border:0;border-radius:6px;padding:11px 18px;font-weight:700;cursor:pointer}}.approve{{background:var(--green);color:white}}.reject{{background:#f6e8e3;color:#9a361c}}
    .reject-form{{margin-top:10px}}.lifecycle{{display:flex;gap:10px;align-items:center;margin-top:20px;padding:13px;background:#f1f4f2;border-radius:8px}}
    .lifecycle span{{color:#99a39e}}.lifecycle .done{{color:var(--green);font-weight:800}}.ids{{font:11px ui-monospace,monospace;color:var(--muted)}}
    .error{{background:#fff0eb;color:#963b20;padding:12px;border-radius:7px}}.empty{{padding:35px;background:white;border:1px dashed #aebbb5}}
    @media(max-width:800px){{.grid{{grid-template-columns:1fr}}.review-form{{grid-template-columns:1fr}}.toolbar{{align-items:stretch;flex-direction:column}}}}
    </style></head><body><header><div><small>TERRASATCH · OPERATOR CONTROL</small><h1>Satchy action control plane</h1></div><a href="/admin">← Admin dashboard</a></header>
    <main>{error}<div class="toolbar"><div><strong>{escape(selected_name)}</strong><div>Receive path remains active; TX is simulated unless explicit RF policy is enabled.</div></div>
    <form method="get"><select name="organization"><option value="">Select organization</option>{"".join(options)}</select><button type="submit">Inspect</button></form></div>
    {"".join(cards)}{empty}</main></body></html>"""
