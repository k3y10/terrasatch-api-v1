"""Server-rendered TerraSatch workspace email pages."""
# ruff: noqa: E501

from __future__ import annotations

from html import escape
from urllib.parse import quote

from terrasatch.brand import SATCHY_ASSET_URL


def _attr(value: object) -> str:
    return escape(str(value), quote=True)


def _styles() -> str:
    return """<style>:root{color-scheme:dark;--bg:#080b0d;--panel:#101519;--line:rgba(255,255,255,.1);--text:#edf1f0;--muted:#8f989e;--orange:#f47a20;--green:#6ee7a0;--yellow:#f6c65b;--mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 70% -20%,rgba(244,122,32,.1),transparent 35%),var(--bg);color:var(--text);font:13px/1.45 Inter,system-ui,sans-serif}header{height:68px;padding:0 28px;border-bottom:1px solid var(--line);display:flex;align-items:center;gap:22px}.brand{display:flex;align-items:center;gap:10px;color:inherit;text-decoration:none;margin-right:auto}.brand img{width:42px;height:42px;object-fit:contain}.brand strong,.brand b{display:block}.brand b{color:var(--orange);font:10px var(--mono);letter-spacing:.11em}main{max-width:1450px;margin:auto;padding:24px 28px}.top{display:flex;justify-content:space-between;gap:18px;align-items:end;margin-bottom:18px}.top h1{margin:0;font-size:30px}.top p{margin:4px 0 0;color:var(--muted)}a{color:#ffad59;text-decoration:none}.panel{border:1px solid var(--line);background:rgba(16,21,25,.94);border-radius:10px;overflow:hidden;margin-bottom:16px}.panel-head{padding:13px 15px;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;gap:12px}.panel-head span{font-weight:800}.panel-head small{color:var(--muted)}table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:12px 14px;border-bottom:1px solid var(--line);vertical-align:top}th{color:var(--muted);font:8px var(--mono);letter-spacing:.08em}.unread td{background:rgba(244,122,32,.045)}.badge{display:inline-block;border:1px solid var(--line);border-radius:99px;padding:2px 7px;color:var(--muted);font:8px var(--mono)}.badge.new{color:var(--orange);border-color:rgba(244,122,32,.4)}.preview{color:var(--muted);font-size:11px;max-width:640px}.compose{display:grid;grid-template-columns:180px 1fr;gap:10px;padding:15px}.compose label{display:grid;gap:5px;color:var(--muted);font-size:10px}.compose .wide{grid-column:1/-1}input,select,textarea{width:100%;background:#0b1013;border:1px solid var(--line);color:var(--text);padding:9px;border-radius:6px}textarea{min-height:125px;resize:vertical}button{border:1px solid rgba(244,122,32,.4);background:rgba(244,122,32,.12);color:#ffad59;padding:9px 12px;border-radius:6px;cursor:pointer}.message{padding:18px}.meta{display:grid;grid-template-columns:110px 1fr;gap:7px 12px;margin-bottom:18px}.meta b{color:var(--muted);font:9px var(--mono)}pre{margin:0;white-space:pre-wrap;overflow-wrap:anywhere;font:13px/1.6 system-ui,sans-serif;color:var(--text)}.attachments{margin-top:18px;padding-top:14px;border-top:1px solid var(--line)}.mail-action{margin:0 0 16px}.mail-action summary{cursor:pointer;padding:12px;color:#ffad59;border:1px solid var(--line);border-radius:6px}.empty{padding:28px;text-align:center;color:var(--muted)}@media(max-width:760px){header,main{padding-left:14px;padding-right:14px}.top{align-items:flex-start;flex-direction:column}.compose{grid-template-columns:1fr}.compose .wide{grid-column:auto}.meta{grid-template-columns:1fr}.table-wrap{overflow:auto}}</style>"""


def _header(title: str) -> str:
    return f'''<header><a class="brand" href="/portal"><img src="{escape(SATCHY_ASSET_URL)}" alt=""><span><strong>TERRASATCH</strong><b>EMAIL WORKSPACE</b></span></a><span>{escape(title)}</span></header>'''


def render_email_inbox(
    *,
    organization_id: str,
    organization_name: str,
    messages: list[dict[str, object]],
    senders: list[str],
    manageable_mailboxes: list[str],
    organization_members: list[dict[str, str]],
    delegates: dict[str, list[dict[str, object]]],
    csrf_token: str,
    embedded: bool = False,
    mailboxes: list[str] | None = None,
) -> str:
    embed_query = "&amp;embedded=1" if embedded else ""
    embed_input = '<input type="hidden" name="embedded" value="1">' if embedded else ""
    workspace_link = "" if embedded else f'<a href="/portal?organization={quote(organization_id)}">Back to workspace</a>'
    rows = []
    for message in messages:
        message_id = _attr(message["id"])
        href = f"/portal/email/{message_id}?organization={quote(organization_id)}{embed_query}"
        unread = not bool(message.get("read"))
        sender = escape(str(message.get("from") or ""))
        subject = escape(str(message.get("subject") or "(no subject)"))
        mailbox = escape(str(message.get("mailbox") or ""))
        preview = escape(str(message.get("preview") or ""))
        timestamp = escape(str(message.get("received_at") or ""))
        direction = escape(str(message.get("direction") or "inbound").upper())
        rows.append(
            f'<tr data-direction="{direction.lower()}" data-mailbox="{_attr(message.get("mailbox") or "")}" class="{"unread" if unread else ""}"><td><span class="badge {"new" if unread else ""}">{direction if not unread else "NEW"}</span></td>'
            f'<td><a href="{href}"><strong>{subject}</strong></a><div class="preview">{preview}</div></td>'
            f"<td>{sender}</td><td>{mailbox}</td><td>{timestamp}</td></tr>"
        )
    table = "".join(rows) or '<tr><td colspan="5" class="empty">Your inbox is ready. Messages from your assigned mailboxes appear here.</td></tr>'
    sender_options = "".join(
        f'<option value="{_attr(sender)}">{escape(sender)}</option>' for sender in senders
    )
    compose = ""
    if sender_options:
        compose = f'''<section class="panel"><div class="panel-head"><span>COMPOSE</span><small>Sent through the verified TerraSatch Resend domain</small></div><form class="compose" method="post" action="/portal/email/compose">{embed_input}<input type="hidden" name="csrf_token" value="{_attr(csrf_token)}"><input type="hidden" name="organization" value="{_attr(organization_id)}"><label>From<select name="sender">{sender_options}</select></label><label>To<input type="email" name="recipient" required></label><label class="wide">Subject<input name="subject" maxlength="500" required></label><label class="wide">Message<textarea name="body" maxlength="20000" required></textarea></label><div class="wide"><button type="submit">Send email</button></div></form></section>'''

    access_sections: list[str] = []
    member_options = "".join(
        f'<option value="{_attr(member.get("email") or "")}">'
        f'{escape(str(member.get("display_name") or member.get("email") or ""))}'
        f' · {escape(str(member.get("email") or ""))}</option>'
        for member in organization_members
        if member.get("email")
    )
    for mailbox in manageable_mailboxes:
        mailbox_delegates = delegates.get(mailbox, [])
        delegate_rows = "".join(
            (
                '<div style="display:flex;justify-content:space-between;gap:12px;'
                'align-items:center;padding:8px 0;border-bottom:1px solid var(--line)">'
                f'<span>{escape(str(item.get("email") or ""))}'
                f' <small style="color:var(--muted)">'
                f'{"view + send" if item.get("can_send") else "view only"}</small></span>'
                '<form method="post" action="/portal/email/access/revoke">'
                f'{embed_input}<input type="hidden" name="csrf_token" value="{_attr(csrf_token)}">'
                f'<input type="hidden" name="organization" value="{_attr(organization_id)}">'
                f'<input type="hidden" name="mailbox" value="{_attr(mailbox)}">'
                f'<input type="hidden" name="delegate_email" value="{_attr(item.get("email") or "")}">'
                '<button type="submit">Revoke</button></form></div>'
            )
            for item in mailbox_delegates
        ) or '<div class="preview">No explicit delegates.</div>'
        send_toggle = '<label style="display:flex;align-items:center;gap:7px"><input style="width:auto" type="checkbox" name="can_send">Allow send and reply</label>'
        if mailbox.casefold() == "billing@terrasatch.com":
            send_toggle = '<p class="preview">Billing access is view-only.</p>'
        access_sections.append(
            '<div style="padding:14px;border-bottom:1px solid var(--line)">'
            f'<strong>{escape(mailbox)}</strong>{delegate_rows}'
            '<form class="compose" method="post" action="/portal/email/access/delegate">'
            f'{embed_input}<input type="hidden" name="csrf_token" value="{_attr(csrf_token)}">'
            f'<input type="hidden" name="organization" value="{_attr(organization_id)}">'
            f'<input type="hidden" name="mailbox" value="{_attr(mailbox)}">'
            f'<label>Delegate<select name="delegate_email" required>{member_options}</select></label>'
            f'<div style="display:flex;align-items:end">{send_toggle}</div>'
            '<div class="wide"><button type="submit">Save access</button></div></form></div>'
        )
    access_panel = ""
    if access_sections:
        access_panel = (
            '<section class="panel"><div class="panel-head"><span>MAILBOX ACCESS</span>'
            '<small>Personal mail stays private. Revoking a delegation does not remove role-based access.</small></div>'
            + "".join(access_sections)
            + "</section>"
        )

    if compose:
        compose = '<details class="mail-action"><summary>Compose email</summary>' + compose + '</details>'
    if access_panel:
        access_panel = '<details class="mail-action"><summary>Manage mailbox access</summary>' + access_panel + '</details>'
    mailbox_options = '<option value="">All assigned mailboxes</option>' + ''.join(f'<option value="{_attr(m)}">{escape(m)}</option>' for m in (mailboxes or sorted(set(senders) | {str(m.get("mailbox") or "") for m in messages})))
    toolbar = f'<div class="mail-toolbar"><div class="folders" aria-label="Email folders"><button type="button" data-folder="inbound" aria-pressed="true">Inbox</button><button type="button" data-folder="outbound" aria-pressed="false">Sent</button><button type="button" data-folder="all" aria-pressed="false">All mail</button></div><label>Mailbox<select id="mailbox-filter">{mailbox_options}</select></label><label>Search loaded messages<input id="mail-search" type="search" placeholder="Search sender or subject"></label></div><p id="mail-results" role="status"></p>'
    behavior = email_controls()
    refresh = f'<a href="/portal/email?organization={quote(organization_id)}{embed_query}">Refresh inbox</a>'
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Email · TerraSatch</title>{_styles()}</head><body>{"" if embedded else _header(organization_name)}<main><section class="top"><div><h1>Email</h1><p>Your personal and assigned team mailboxes.</p></div>{workspace_link}</section>{compose}{toolbar}<section class="panel"><div class="panel-head"><span id="folder-label">INBOX</span><small>{len(messages)} message(s) · {refresh}</small></div><div class="table-wrap"><table><thead><tr><th>STATE</th><th>SUBJECT</th><th>FROM</th><th>MAILBOX</th><th>TIME</th></tr></thead><tbody>{table}</tbody></table></div></section>{access_panel}</main>{behavior}</body></html>'''


def render_email_detail(
    *,
    organization_id: str,
    organization_name: str,
    message: object,
    reply_allowed: bool,
    csrf_token: str,
    embedded: bool = False,
) -> str:
    embed_query = "&amp;embedded=1" if embedded else ""
    embed_input = '<input type="hidden" name="embedded" value="1">' if embedded else ""
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
                f'{quote(str(item.get("id") or ""), safe="")}?organization={quote(organization_id)}" target="_blank" rel="noopener noreferrer">'
                f'{escape(str(item.get("filename") or "attachment"))}</a>'
                f' · {escape(str(item.get("content_type") or "file"))}</li>'
            )
            for item in attachments
            if isinstance(item, dict) and item.get("id")
        )
        attachment_html = f'<div class="attachments"><strong>Attachments</strong><ul>{items}</ul></div>'
    reply = ""
    if reply_allowed and getattr(message, "direction", "") == "inbound":
        reply = f'''<section class="panel"><div class="panel-head"><span>REPLY</span><small>From {mailbox}</small></div><form class="compose" method="post" action="/portal/email/{_attr(message.id)}/reply">{embed_input}<input type="hidden" name="csrf_token" value="{_attr(csrf_token)}"><input type="hidden" name="organization" value="{_attr(organization_id)}"><label class="wide">Message<textarea id="reply-body" name="body" maxlength="20000" required></textarea></label><div class="wide"><button id="support-draft" type="button" data-url="/api/v1/workspace/organizations/{quote(organization_id)}/email/{_attr(message.id)}/draft" data-csrf="{_attr(csrf_token)}">Draft with Satchy</button><p id="draft-status" role="status">Review the draft before sending. Satchy does not reply automatically.</p><button type="submit">Send reply</button></div></form></section>'''
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{subject} · TerraSatch</title>{_styles()}</head><body>{"" if embedded else _header(organization_name)}<main><section class="top"><div><h1>{subject}</h1><p>{escape(str(getattr(message, "direction", "inbound")).upper())}</p></div><a href="/portal/email?organization={quote(organization_id)}{embed_query}">Back to inbox</a></section><section class="panel"><div class="message"><div class="meta"><b>FROM</b><span>{sender}</span><b>TO</b><span>{recipients}</span><b>MAILBOX</b><span>{mailbox}</span><b>RECEIVED</b><span>{timestamp}</span></div><pre>{body or "(No plain-text body was supplied.)"}</pre>{attachment_html}</div></section>{reply}</main>{support_draft_script()}</body></html>'''


def email_controls() -> str:
    return """<style>.mail-toolbar{display:flex;gap:16px;align-items:end;flex-wrap:wrap;margin:18px 0}.mail-toolbar label{font-size:11px;color:var(--muted);flex:1;min-width:140px}.folders{display:flex;gap:4px}.folders button{background:none;border:0;border-bottom:2px solid transparent;border-radius:0;color:var(--muted)}.folders button[aria-pressed=true]{color:#f59e0b;border-color:#f59e0b}.mail-action>summary{display:inline-block;background:#f59e0b;color:#101010;font-weight:700;border:0}.top h1{font-size:25px}.panel{border-radius:4px}th{font-size:10px}.empty{padding:90px 24px}#mail-results{color:var(--muted);font-size:11px}tr[hidden]{display:none}button,input,select,textarea{font-family:inherit}main{padding:12px}input:focus-visible,select:focus-visible,button:focus-visible,summary:focus-visible{outline:2px solid #f59e0b;outline-offset:2px}</style><script>(()=>{let folder='inbound';const rows=[...document.querySelectorAll('tr[data-direction]')],search=document.getElementById('mail-search'),mailbox=document.getElementById('mailbox-filter');function filter(){document.getElementById('folder-label').textContent=folder==='outbound'?'SENT':folder==='all'?'ALL MAIL':'INBOX';let count=0;for(const row of rows){const match=(folder==='all'||row.dataset.direction===folder)&&(!mailbox.value||row.dataset.mailbox===mailbox.value)&&row.textContent.toLowerCase().includes(search.value.toLowerCase());row.hidden=!match;if(match)count++}document.getElementById('mail-results').textContent=count+' matching messages in the latest '+rows.length+' loaded. Refresh inbox for new messages.'}document.querySelectorAll('[data-folder]').forEach(button=>button.addEventListener('click',()=>{folder=button.dataset.folder;document.querySelectorAll('[data-folder]').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));filter()}));search.addEventListener('input',filter);mailbox.addEventListener('change',filter);filter()})();</script>"""


def support_draft_script() -> str:
    return """<script>(()=>{const button=document.getElementById('support-draft');if(!button)return;button.addEventListener('click',async()=>{const body=document.getElementById('reply-body'),status=document.getElementById('draft-status');if(body.value.trim()){status.textContent='Your reply already contains text. Clear it first if you want a new Satchy draft.';return}button.disabled=true;status.textContent='Preparing a draft for your review…';const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),50000);try{const r=await fetch(button.dataset.url,{method:'POST',credentials:'same-origin',signal:controller.signal,headers:{'X-CSRF-Token':button.dataset.csrf,Accept:'application/json'}});const data=await r.json();if(!r.ok)throw Error(typeof data.detail==='string'?data.detail:'Satchy is unavailable. Write your reply manually.');body.value=data.draft;status.textContent='Draft ready. Verify the facts and edit before selecting Send reply. Nothing has been sent.'}catch(e){status.textContent=e.name==='AbortError'?'Satchy took too long. You can write a reply manually.':e.message}finally{clearTimeout(timer);button.disabled=false}})})();</script>"""
