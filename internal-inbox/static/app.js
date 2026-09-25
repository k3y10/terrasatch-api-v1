const $ = id => document.getElementById(id);
let session, folder = "inbox", messages = [];
const labels = { inbox: "Inbox", draft: "Drafts", sent: "Sent", pending: "Needs review" };
const feedback = text => { $("feedback").textContent = text; };
async function api(path, method = "GET", body) {
  const response = await fetch(path, { method, headers: { "Content-Type": "application/json", "X-CSRF-Token": session?.csrf || "" }, body: body ? JSON.stringify(body) : undefined });
  const data = await response.json();
  if (response.status === 401) { session = null; messages = []; $("messages").replaceChildren(); $("reader").replaceChildren(); $("composer").close(); $("login").hidden = false; $("workspace").hidden = true; $("logout").hidden = true; $("identity").textContent = "Private team access"; }
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Request could not be completed");
  return data;
}
function element(tag, text, className) { const node = document.createElement(tag); node.textContent = text; if (className) node.className = className; return node; }
async function loadSession() {
  try {
    session = await api("/api/session"); $("login").hidden = true; $("workspace").hidden = false; $("logout").hidden = false;
    $("identity").textContent = session.user; $("mailbox").replaceChildren();
    session.mailboxes.forEach(mailbox => { const option = element("option", mailbox); option.value = mailbox; $("mailbox").append(option); });
    $("connection").textContent = session.sending_enabled ? `Sending enabled · internal budget ${session.daily_limit}/day, ${session.monthly_limit}/31 days. Provider acceptance is not delivery confirmation.` : "Setup mode · drafts work. Sending stays off until email-provider and domain setup are verified.";
    await refresh();
  } catch { session = null; $("login").hidden = false; $("workspace").hidden = true; $("logout").hidden = true; }
}
async function refresh() {
  try { messages = await api(`/api/messages?mailbox=${encodeURIComponent($("mailbox").value)}&folder=${folder}`); renderList(); $("reader").replaceChildren(element("h2", "Choose a conversation"), element("p", "Messages are private to the mailboxes assigned to your account.")); }
  catch (error) { feedback(error.message); }
}
function renderList() {
  $("messages").replaceChildren(); const query = $("search").value.toLowerCase();
  const found = messages.filter(m => `${m.sender} ${m.subject} ${m.body}`.toLowerCase().includes(query));
  if (!found.length) $("messages").append(element("p", query ? "No matching messages." : "No messages here yet."));
  found.forEach(message => { const row = element("button", "", "message-row"); row.append(element("small", message.sender), element("strong", message.subject), element("small", new Date(message.created * 1000).toLocaleString())); row.onclick = () => read(message); $("messages").append(row); });
}
function read(message) {
  $("reader").replaceChildren(element("p", labels[message.folder], "kicker"), element("h2", message.subject), element("p", `From ${message.sender} · To ${message.recipient}`, "muted"), element("pre", message.body));
  if (message.folder === "draft") {
    const send = element("button", "Send this draft →", "primary"); send.disabled = !session.sending_enabled;
    send.onclick = async () => { if (!confirm(`Send this message from ${message.mailbox} to ${message.recipient}?`)) return; send.disabled = true; try { await api(`/api/messages/${message.id}/send`, "POST"); feedback("Accepted by the email provider. Delivery is not yet confirmed."); await refresh(); } catch (e) { feedback(e.message); await refresh(); } };
    $("reader").append(send);
  }
  if (message.folder === "pending") $("reader").append(element("p", "Check the provider receipt before retrying. Automatic resend is disabled to avoid duplicates."));
}
$("login-form").onsubmit = async event => { event.preventDefault(); try { await api("/api/login", "POST", { username: $("username").value, password: $("password").value }); $("password").value = ""; feedback(""); await loadSession(); } catch (e) { feedback(e.message); } };
$("logout").onclick = async () => { try { await api("/api/logout", "POST"); location.reload(); } catch (e) { feedback(e.message); } };
$("refresh").onclick = refresh; $("mailbox").onchange = refresh; $("search").oninput = renderList;
document.querySelectorAll("[data-folder]").forEach(button => { button.onclick = () => { folder = button.dataset.folder; document.querySelectorAll("[data-folder]").forEach(b => b.classList.toggle("selected", b === button)); $("folder-title").textContent = labels[folder]; refresh(); }; });
$("compose").onclick = () => { $("from").textContent = "From " + $("mailbox").value; $("composer").showModal(); };
$("close-compose").onclick = () => $("composer").close();
$("draft-form").onsubmit = async event => { event.preventDefault(); const button = event.submitter; button.disabled = true; try { await api("/api/drafts", "POST", { mailbox: $("mailbox").value, recipient: $("recipient").value, subject: $("subject").value, body: $("body").value }); $("draft-form").reset(); $("composer").close(); feedback("Draft saved. Nothing has been sent."); document.querySelector('[data-folder="draft"]').click(); } catch (e) { feedback(e.message); } finally { button.disabled = false; } };
loadSession();
