"""Server-rendered TerraSatch workspace email pages."""
# ruff: noqa: E501

from __future__ import annotations

from html import escape
from urllib.parse import quote

from terrasatch.brand import SATCHY_ASSET_URL


def _attr(value: object) -> str:
    return escape(str(value), quote=True)


def _styles() -> str:
    return """<style>:root{color-scheme:dark;--bg:#080b0d;--panel:#101519;--line:rgba(255,255,255,.1);--text:#edf1f0;--muted:#8f989e;--orange:#f47a20;--green:#6ee7a0;--yellow:#f6c65b;--mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 70% -20%,rgba(244,122,32,.1),transparent 35%),var(--bg);color:var(--text);font:13px/1.45 Inter,system-ui,sans-serif}header{height:68px;padding:0 28px;border-bottom:1px solid var(--line);display:flex;align-items:center;gap:22px}.brand{display:flex;align-items:center;gap:10px;color:inherit;text-decoration:none;margin-right:auto}.brand img{width:42px;height:42px;object-fit:contain}.brand strong,.brand b{display:block}.brand b{color:var(--orange);font:10px var(--mono);letter-spacing:.11em}main{max-width:1450px;margin:auto;padding:24px 28px}.top{display:flex;justify-content:space-between;gap:18px;align-items:end;margin-bottom:18px}.top h1{margin:0;font-size:30px}.top p{margin:4px 0 0;color:var(--muted)}a{color:#ffad59;text-decoration:none}.panel{border:1px solid var(--line);background:rgba(16,21,25,.94);border-radius:10px;overflow:hidden;margin-bottom:16px}.panel-head{padding:13px 15px;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;gap:12px}.panel-head span{font-weight:800}.panel-head small{color:var(--muted)}table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:12px 14px;border-bottom:1px solid var(--line);vertical-align:top}th{color:var(--muted);font:8px var(--mono);letter-spacing:.08em}.unread td{background:rgba(244,122,32,.045)}.badge{display:inline-block;border:1px solid var(--line);border-radius:99px;padding:2px 7px;color:var(--muted);font:8px var(--mono)}.badge.new{color:var(--orange);border-color:rgba(244,122,32,.4)}.preview{color:var(--muted);font-size:11px;max-width:640px}.compose{display:grid;grid-template-columns:180px 1fr;gap:10px;padding:15px}.compose label{display:grid;gap:5px;color:var(--muted);font-size:10px}.compose .wide{grid-column:1/-1}input,select,textarea{width:100%;background:#0b1013;border:1px solid var(--line);color:var(--text);padding:9px;border-radius:6px}textarea{min-height:125px;resize:vertical}button{border:1px solid rgba(244,122,32,.4);background:rgba(244,122,32,.12);color:#ffad59;padding:9px 12px;border-radius:6px;cursor:pointer}.message{padding:18px}.meta{display:grid;grid-template-columns:110px 1fr;gap:7px 12px;margin-bottom:18px}.meta b{color:var(--muted);font:9px var(--mono)}pre{margin:0;white-space:pre-wrap;overflow-wrap:anywhere;font:13px/1.6 system-ui,sans-serif;color:var(--text)}.attachments{margin-top:18px;padding-top:14px;border-top:1px solid var(--line)}.empty{padding:28px;text-align:center;color:var(--muted)}@media(max-width:760px){header,main{padding-left:14px;padding-right:14px}.top{align-items:flex-start;flex-direction:column}.compose{grid-template-columns:1fr}.compose .wide{grid-column:auto}.meta{grid-template-columns:1fr}.table-wrap{overflow:auto}}</style>"""


def _header(title: str) -> str:
    return f'''<header><a class="brand" href="/portal"><img src="{escape(SATCHY_ASSET_URL)}" alt=""><span><strong>TERRASATCH</strong><b>EMAIL WORKSPACE</b></span></a><span>{escape(title)}</span></header>'''


def render_email_inbox(
    *,
    organization_id: str,
    organization_name: str,
    messages: list[dict[str, object]],
    senders: list[str],
    csrf_token: str,
) -> str:
    rows = []
    for message in messages:
        message_id = _attr(message["id"])
        href = f"/portal/email/{message_id}?organization={quote(organization_id)}"
        unread = not bool(message.get("read"))
        sender = escape(str(message.get("from") or ""))
        subject = escape(str(message.get("subject") or "(no subject)"))
        mailbox = escape(str(message.get("mailbox") or ""))
        preview = escape(str(message.get("preview") or ""))
        timestamp = escape(str(message.get("received_at") or ""))
        direction = escape(str(message.get("direction") or "inbound").upper())
        rows.append(
            f'<tr class="{"unread" if unread else ""}"><td><span class="badge {"new" if unread else ""}">{direction if not unread else "NEW"}</span></td>'
            f'<td><a href="{href}"><strong>{subject}</strong></a><div class="preview">{preview}</div></td>'
            f"<td>{sender}</td><td>{mailbox}</td><td>{timestamp}</td></tr>"
        )
    table = "".join(rows) or '<tr><td colspan="5" class="empty">No TerraSatch email has been received yet.</td></tr>'
    sender_options = "".join(
        f'<option value="{_attr(sender)}">{escape(sender)}</option>' for sender in senders
    )
    compose = ""
    if sender_options:
        compose = f'''<section class="panel"><div class="panel-head"><span>COMPOSE</span><small>Sent through the verified TerraSatch Resend domain</small></div><form class="compose" method="post" action="/portal/email/compose"><input type="hidden" name="csrf_token" value="{_attr(csrf_token)}"><input type="hidden" name="organization" value="{_attr(organization_id)}"><label>From<select name="sender">{sender_options}</select></label><label>To<input type="email" name="recipient" required></label><label class="wide">Subject<input name="subject" maxlength="500" required></label><label class="wide">Message<textarea name="body" maxlength="20000" required></textarea></label><div class="wide"><button type="submit">Send email</button></div></form></section>'''
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Email · TerraSatch</title>{_styles()}</head><body>{_header(organization_name)}<main><section class="top"><div><h1>Email</h1><p>Inbound and human-sent TerraSatch messages in the field workspace.</p></div><a href="/portal?organization={quote(organization_id)}">Back to workspace</a></section>{compose}<section class="panel"><div class="panel-head"><span>INBOX</span><small>{len(messages)} message(s)</small></div><div class="table-wrap"><table><thead><tr><th>STATE</th><th>SUBJECT</th><th>FROM</th><th>MAILBOX</th><th>TIME</th></tr></thead><tbody>{table}</tbody></table></div></section></main></body></html>'''


def render_email_detail(
    *,
    organization_id: str,
    organization_name: str,
    message: object,
    reply_allowed: bool,
    csrf_token: str,
) -> str:
    subject = escape(str(getattr(message, "subject", "") or "(no subject)"))
    sender = escape(str(getattr(message, "from_address", "") or ""))
    mailbox = escape(str(getattr(message, "received_for", "") or ""))
    recipients = escape(", ".join(getattr(message, "to_addresses", []) or []))
    timestamp = escape(str(getattr(message, "received_at", "") or ""))
    body = escape(str(getattr(message, "text_body", "") or ""))
    attachments = getattr(message, "attachments", []) or []
    attachment_html = ""
    if attachments:
        items = "".join(
            (
                f'<li><a href="/portal/email/{_attr(message.id)}/attachments/'
                f'{_attr(item.get("id") or "")}?organization={quote(organization_id)}">'
                f'{escape(str(item.get("filename") or "attachment"))}</a>'
                f' · {escape(str(item.get("content_type") or "file"))}</li>'
            )
            for item in attachments
            if isinstance(item, dict) and item.get("id")
        )
        attachment_html = f'<div class="attachments"><strong>Attachments</strong><ul>{items}</ul></div>'
    reply = ""
    if reply_allowed and getattr(message, "direction", "") == "inbound":
        reply = f'''<section class="panel"><div class="panel-head"><span>REPLY</span><small>From {mailbox}</small></div><form class="compose" method="post" action="/portal/email/{_attr(message.id)}/reply"><input type="hidden" name="csrf_token" value="{_attr(csrf_token)}"><input type="hidden" name="organization" value="{_attr(organization_id)}"><label class="wide">Message<textarea name="body" maxlength="20000" required></textarea></label><div class="wide"><button type="submit">Send reply</button></div></form></section>'''
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{subject} · TerraSatch</title>{_styles()}</head><body>{_header(organization_name)}<main><section class="top"><div><h1>{subject}</h1><p>{escape(str(getattr(message, "direction", "inbound")).upper())}</p></div><a href="/portal/email?organization={quote(organization_id)}">Back to inbox</a></section><section class="panel"><div class="message"><div class="meta"><b>FROM</b><span>{sender}</span><b>TO</b><span>{recipients}</span><b>MAILBOX</b><span>{mailbox}</span><b>RECEIVED</b><span>{timestamp}</span></div><pre>{body or "(No plain-text body was supplied.)"}</pre>{attachment_html}</div></section>{reply}</main></body></html>'''
