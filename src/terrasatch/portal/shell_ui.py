"""Lightweight, progressively enhanced navigation for the authenticated workspace."""

# ruff: noqa: E501
from html import escape
from urllib.parse import quote

from .assistant_ui import assistant_panel, assistant_script, assistant_styles


def workspace_content(
    *,
    selected_organization: str,
    email: str,
    display_name: str,
    role: str,
    overview: str,
    devices: str,
    billing: str,
    csrf_token: str = "",
) -> str:

    internal = email.strip().casefold().endswith("@terrasatch.com")

    email_url = (
        "/portal/email?organization=" + quote(selected_organization, safe="") + "&embedded=1"
    )

    email_panel = (
        '<p class="section-intro">Your assigned team mailboxes, inside your workspace. Mailbox access is checked separately from your organization role.</p>'
        f'<iframe id="workspace-inbox" data-src="{escape(email_url, quote=True)}" title="TerraSatch team email" referrerpolicy="same-origin"></iframe>'
        "<noscript><p>Enable JavaScript to use email inside this workspace.</p>"
        f'<a href="{escape(email_url.replace("&embedded=1", ""), quote=True)}">Open team email</a></noscript>'
        if internal
        else '<div class="workspace-card"><span class="state-label">NOT AVAILABLE FOR THIS ACCOUNT</span><h3>Organization email</h3>'
        "<p>The current email beta supports assigned internal TerraSatch mailboxes. Customer organization email is not enabled. Your account and device access are unchanged.</p></div>"
    )

    return f"""<div class="workspace-layout"><nav class="workspace-nav" aria-label="Workspace sections">

<a href="#overview" data-section="overview" aria-current="page">Overview</a>

<a href="#email" data-section="email">Email <span>Beta</span></a>

<a href="#devices" data-section="devices">Devices</a>

<a href="#services" data-section="services">Tools &amp; services</a>

<a href="#account" data-section="account">Account &amp; access</a>

<p>LISTEN · WATCH<br>LEARN · ADAPT</p></nav><div class="workspace-content">

<section id="overview" class="workspace-section" aria-labelledby="overview-title"><div class="section-heading"><div><span class="eyebrow">CONNECTED WORKSPACE</span><h2 id="overview-title" tabindex="-1">Your organization at a glance</h2><p>Review field activity, open your tools, and see the access connected to your account.</p></div><a class="refresh-link" href="?organization={quote(selected_organization, safe="")}#overview">Refresh status</a></div>{overview}

<div class="workspace-cards"><a class="workspace-card" href="#devices"><span class="state-label">CONNECTED DEVICES</span><h3>Your Edge fleet <span aria-hidden="true">→</span></h3><p>Review device health, hardware, and receive or transmit readiness.</p></a><a class="workspace-card" href="#email"><span class="state-label">{"INTERNAL EMAIL BETA" if internal else "NOT ENABLED"}</span><h3>Team email <span aria-hidden="true">→</span></h3><p>{"Open your assigned mailboxes without leaving this workspace." if internal else "Customer organization email is not available yet."}</p></a><a class="workspace-card" href="#account"><span class="state-label">YOUR ACCOUNT</span><h3>Membership &amp; access <span aria-hidden="true">→</span></h3><p>See your organization role, subscription status, and available controls.</p></a></div><p class="snapshot-note">Status is a snapshot from this page load. Refresh when you need an update.</p></section>

<section id="email" class="workspace-section" aria-labelledby="email-title"><div class="section-heading"><div><span class="eyebrow">COMMUNICATION</span><h2 id="email-title" tabindex="-1">Team email</h2></div></div>{email_panel}</section>

<section id="devices" class="workspace-section" aria-labelledby="devices-title"><div class="section-heading"><div><span class="eyebrow">FIELD SYSTEMS</span><h2 id="devices-title" tabindex="-1">Connected devices</h2><p>Devices visible to your selected organization membership.</p></div><a class="refresh-link" href="?organization={quote(selected_organization, safe="")}#devices">Refresh devices</a></div>{devices}</section>

<section id="services" class="workspace-section" aria-labelledby="services-title"><div class="section-heading"><div><span class="eyebrow">CONNECTED TO YOUR ORGANIZATION</span><h2 id="services-title" tabindex="-1">Tools &amp; services</h2><p>Connection status and available capabilities from your workspace API. Availability does not grant subscription or mailbox access.</p></div><button id="refresh-services" type="button">Refresh services</button></div><p id="services-status" role="status" aria-live="polite">Open this section to load services.</p><div id="services-list" class="workspace-cards" data-url="/api/v1/workspace/organizations/{quote(selected_organization, safe="")}/integrations/catalog"></div></section>

<section id="account" class="workspace-section" aria-labelledby="account-title"><div class="section-heading"><div><span class="eyebrow">IDENTITY &amp; ENTITLEMENTS</span><h2 id="account-title" tabindex="-1">Account &amp; access</h2></div></div><div class="workspace-card account-identity"><h3>{escape(display_name)}</h3><p>{escape(email)}</p><strong>ROLE · {escape(role.upper())}</strong><p>Organization membership controls which field systems you can see. Billing management requires owner or administrator permission. Mailbox permissions are assigned separately.</p></div>{billing}<div class="workspace-card"><h3>Connected tools</h3><p>Device capabilities come from the connected hardware and provider. Radio transmission remains operator-controlled. Subscription status alone does not activate hardware or grant mailbox access.</p><p>Radio operation is available through your authorized field console.</p></div></section>

</div>{assistant_panel(selected_organization, csrf_token)}</div>{_navigation_script()}{assistant_script()}{assistant_styles()}"""


def _navigation_script() -> str:

    return """<script>(()=>{const names=['overview','email','devices','services','account'];const sections=[...document.querySelectorAll('.workspace-section')];const links=[...document.querySelectorAll('.workspace-nav [data-section]')];let servicesLoaded=false;let servicesLoading=false;async function loadServices(){if(servicesLoading)return;servicesLoading=true;const status=document.getElementById('services-status');const list=document.getElementById('services-list');const button=document.getElementById('refresh-services');button.disabled=true;list.replaceChildren();status.textContent='Loading your organization services…';const controller=new AbortController();const timeout=setTimeout(()=>controller.abort(),12000);try{const response=await fetch(list.dataset.url,{credentials:'same-origin',cache:'no-store',signal:controller.signal,headers:{Accept:'application/json'}});if(response.status===401){const login=document.createElement('a');login.href='/portal/login';login.textContent='Sign in again';list.append(login);throw new Error('Your session has expired. Sign in again to load services.');}if(response.status===403)throw new Error('Your account cannot view services for this organization.');if(!response.ok)throw new Error('Services are temporarily unavailable. Try refreshing.');const items=await response.json();if(!Array.isArray(items))throw new Error('Services returned an unexpected response. Try refreshing.');list.replaceChildren();for(const item of items){const card=document.createElement('article');card.className='workspace-card';const heading=document.createElement('h3');heading.textContent=item.name||'Service';const state=document.createElement('span');state.className='state-label';state.textContent=item.support_status==='managed'?'MANAGED SERVICE':item.connected?(item.runtime_ready?'CONNECTED':'CONNECTED · SETUP NEEDED'):String(item.connect_status||'unknown').replaceAll('_',' ').toUpperCase();const description=document.createElement('p');description.textContent=item.description||'';const access=document.createElement('p');access.textContent=item.support_status==='managed'?'Managed by TerraSatch; device availability is shown in Devices.':item.requires_admin?'Setup requires an organization administrator.':item.allowed?'Your role can request supported connections.':'Connection setup is not available for this service yet.';const capabilities=document.createElement('p');capabilities.textContent='Capabilities: '+(Array.isArray(item.capability_details)&&item.capability_details.length?item.capability_details.map(c=>c.label).join(', '):'No workflow capabilities listed');card.append(state,heading,description,access,capabilities);list.append(card)}servicesLoaded=true;status.textContent=items.length+' services · updated just now. Refresh to check for changes.'}catch(error){status.textContent=error.name==='AbortError'?'Services took too long to respond. Try refreshing.':error.message;servicesLoaded=false}finally{clearTimeout(timeout);servicesLoading=false;button.disabled=false}}document.getElementById('refresh-services').addEventListener('click',loadServices);function show(focus){const requested=location.hash.slice(1);const name=names.includes(requested)?requested:'overview';sections.forEach(section=>{section.hidden=section.id!==name});links.forEach(link=>{if(link.dataset.section===name)link.setAttribute('aria-current','page');else link.removeAttribute('aria-current')});if(name==='services'&&!servicesLoaded)loadServices();if(name==='email'){const frame=document.getElementById('workspace-inbox');if(frame&&!frame.hasAttribute('src'))frame.setAttribute('src',frame.dataset.src)}if(focus)document.getElementById(name+'-title').focus({preventScroll:true})}window.addEventListener('hashchange',()=>show(true));const orgForm=document.getElementById('organization-form');orgForm.addEventListener('submit',()=>{orgForm.action='/portal'+(names.includes(location.hash.slice(1))?location.hash:'#overview')});show(false)})();</script>"""


def workspace_styles() -> str:

    return """<style>:root{--orange:#f59e0b}.workspace-layout{display:grid;grid-template-columns:195px minmax(0,1fr);gap:28px;margin-top:28px}.workspace-nav{align-self:start;position:sticky;top:20px;display:grid;gap:6px}.workspace-nav a{padding:13px 12px;border:1px solid transparent;border-radius:6px;color:var(--muted);text-decoration:none;font-weight:600}.workspace-nav a:hover,.workspace-nav a[aria-current]{border-color:#574020;background:#f59e0b0d;color:#ffbd45}.workspace-nav a span{font:9px var(--mono);margin-left:8px;color:var(--muted)}.workspace-nav p{font:9px/1.9 var(--mono);letter-spacing:.12em;color:var(--muted);padding:12px}.workspace-content{min-width:0}.workspace-section[hidden]{display:none}.workspace-section{scroll-margin-top:20px}.workspace-section+.workspace-section{margin-top:28px}.workspace-section[hidden]+.workspace-section{margin-top:0}.section-heading{display:flex;justify-content:space-between;gap:20px;align-items:center;margin-bottom:22px}.section-heading h2{font-size:25px;line-height:1.2;margin:7px 0}.section-heading p,.section-intro{color:var(--muted);line-height:1.6;margin:0}.eyebrow,.state-label{font:9px var(--mono);letter-spacing:.1em;color:var(--orange)}.refresh-link{white-space:nowrap;color:var(--orange);font-size:12px}.workspace-cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;margin-top:22px}.workspace-card{display:block;border:1px solid var(--line);border-radius:9px;padding:20px;background:var(--panel);color:var(--text);text-decoration:none;overflow-wrap:anywhere}.workspace-card h3{font-size:17px;margin:10px 0}.workspace-card h3 span{float:right;color:var(--orange)}.workspace-card p{color:var(--muted);line-height:1.6;margin:8px 0}.workspace-card a{color:var(--orange)}a.workspace-card:hover{border-color:#806032}.snapshot-note{color:var(--muted);font-size:11px;margin-top:18px}.account-identity{margin-bottom:18px}.account-identity strong{color:var(--orange);font:11px var(--mono)}#workspace-inbox{display:block;width:100%;min-height:720px;height:calc(100vh - 240px);border:1px solid var(--line);border-radius:10px;margin-top:20px;background:var(--bg)}a:focus-visible,button:focus-visible,select:focus-visible{outline:2px solid var(--orange);outline-offset:4px}.skip-link{position:absolute;left:16px;top:-60px;padding:10px;background:var(--panel);color:var(--orange);z-index:10}.skip-link:focus{top:8px}.organization-controls{display:flex;align-items:end;gap:8px}.organization-controls select{max-width:300px;width:100%}.headline h1{overflow-wrap:anywhere}.headline label{font-size:11px}.metrics span,th{font-size:10px}.metrics b{font-size:22px}.billing p,.policy span{font-size:12px}.panel-head a{font-size:12px}.who span{font-size:11px}.section-heading h2:focus{outline:none}@media(max-width:1100px){.workspace-cards{grid-template-columns:1fr}.workspace-layout{grid-template-columns:165px minmax(0,1fr);gap:20px}}@media(max-width:700px){header{height:auto;min-height:68px;flex-wrap:wrap;padding:12px 14px;gap:10px}.workspace-layout{display:block;margin-top:20px}.workspace-nav{position:static;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));margin-bottom:24px;gap:8px}.workspace-nav a{background:var(--panel);border-color:var(--line);font-size:12px}.workspace-nav p{display:none}.section-heading{align-items:start;flex-direction:column;gap:10px}.section-heading h2{font-size:23px}.organization-controls label{flex:1;min-width:0}.organization-controls select{max-width:100%}.workspace-card{padding:17px}#workspace-inbox{min-height:800px}.panel-head{gap:12px}.metrics b{font-size:20px}}</style>"""
