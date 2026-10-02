"use client";

import Image from "next/image";
import { useEffect, useMemo, useState } from "react";
import { TerraSatchApiError, TerraSatchClient } from "@terrasatch/sdk";

const API_ORIGIN =
  process.env.NEXT_PUBLIC_TERRASATCH_API_ORIGIN || "https://api.terrasatch.com";

const client = new TerraSatchClient({
  baseUrl: API_ORIGIN,
  credentials: "include",
});

function messageFor(error) {
  if (error instanceof TerraSatchApiError) {
    if (error.status === 401) return "Your TerraSatch session has expired. Sign in again.";
    if (error.status === 403) return error.message || "This action is not available for your account.";
    return error.message;
  }
  return error instanceof Error ? error.message : "Something went wrong.";
}

function StatusPill({ children, tone = "neutral" }) {
  return <span className={`pill pill-${tone}`}>{children}</span>;
}

function Login({ csrfToken, onSignedIn }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const bootstrap = csrfToken ? { csrf_token: csrfToken } : await client.workspaceSession();
      await client.loginWorkspace(email.trim(), password, bootstrap.csrf_token);
      setPassword("");
      await onSignedIn();
    } catch (err) {
      setError(messageFor(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="login-page">
      <section className="login-card">
        <div className="brand-lockup">
          <Image
            src="https://api.terrasatch.com/assets/satchy.png"
            width={74}
            height={74}
            alt="Satchy"
            priority
          />
          <div>
            <span className="eyebrow">TERRASATCH</span>
            <h1>Satchy</h1>
          </div>
        </div>
        <p className="login-copy">
          Sign in with your TerraSatch account. Your identity, organizations, and
          permissions stay in the TerraSatch API.
        </p>
        <form onSubmit={submit} className="login-form">
          <label>
            Email
            <input
              type="email"
              autoComplete="username"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="you@terrasatch.com"
              required
            />
          </label>
          <label>
            Password
            <input
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
          </label>
          {error ? <p className="error" role="alert">{error}</p> : null}
          <button className="primary" type="submit" disabled={busy}>
            {busy ? "Signing in…" : "Open Satchy"}
          </button>
        </form>
        <p className="security-note">
          Satchy does not maintain a second user database. Authentication is handled by
          <strong> api.terrasatch.com</strong>.
        </p>
      </section>
    </main>
  );
}

function AppShell({ session, onRefreshSession, onSignedOut }) {
  const [organizationId, setOrganizationId] = useState(
    session.organizations[0]?.id || "",
  );
  const [workspace, setWorkspace] = useState(null);
  const [runs, setRuns] = useState([]);
  const [conversation, setConversation] = useState([]);
  const [prompt, setPrompt] = useState("");
  const [loadingWorkspace, setLoadingWorkspace] = useState(false);
  const [sending, setSending] = useState(false);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");

  const organization = useMemo(
    () => session.organizations.find((item) => item.id === organizationId),
    [session.organizations, organizationId],
  );

  async function loadWorkspace(target = organizationId) {
    if (!target) return;
    setLoadingWorkspace(true);
    setError("");
    try {
      const [snapshot, recentRuns] = await Promise.all([
        client.getWorkspace(target),
        client.listSatchyRuns(target, 12),
      ]);
      setWorkspace(snapshot);
      setRuns(recentRuns);
    } catch (err) {
      if (err instanceof TerraSatchApiError && err.status === 401) {
        await onRefreshSession();
        return;
      }
      setError(messageFor(err));
    } finally {
      setLoadingWorkspace(false);
    }
  }

  useEffect(() => {
    loadWorkspace();
    // organizationId is the intentional refresh boundary.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [organizationId]);

  async function sendMessage(event) {
    event.preventDefault();
    const text = prompt.trim();
    if (!text || !organizationId || sending) return;
    setSending(true);
    setStatus("Satchy is reviewing your workspace…");
    setError("");
    setConversation((items) => [...items, { role: "user", text }]);
    setPrompt("");

    try {
      const result = await client.chatWithSatchy(
        organizationId,
        {
          request_id: crypto.randomUUID(),
          message: text,
        },
        session.csrf_token,
      );
      setConversation((items) => [
        ...items,
        {
          role: "assistant",
          text: result.answer,
          approvalRequired: result.approval_required,
          runId: result.run_id,
        },
      ]);
      setStatus(
        result.approval_required
          ? "A proposal was prepared. Nothing has been sent without approval."
          : "Response ready.",
      );
      await loadWorkspace(organizationId);
    } catch (err) {
      setConversation((items) => items.slice(0, -1));
      setPrompt(text);
      setError(messageFor(err));
      setStatus("");
    } finally {
      setSending(false);
    }
  }

  async function signOut() {
    setError("");
    try {
      await client.logoutWorkspace(session.csrf_token);
    } catch (err) {
      if (!(err instanceof TerraSatchApiError && err.status === 401)) {
        setError(messageFor(err));
        return;
      }
    }
    onSignedOut();
  }

  const pendingActions =
    workspace?.actions?.filter((item) =>
      ["proposed", "awaiting_approval"].includes(item.status),
    ) || [];
  const connectedTools = workspace?.integrations?.connections?.length || 0;
  const records = workspace?.records?.length || 0;
  const sites = workspace?.sites?.length || 0;

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="top-brand">
          <Image
            src="https://api.terrasatch.com/assets/satchy.png"
            width={42}
            height={42}
            alt=""
          />
          <div>
            <strong>SATCHY</strong>
            <span>by TerraSatch</span>
          </div>
        </div>
        <div className="top-actions">
          {session.organizations.length > 1 ? (
            <select
              aria-label="Organization"
              value={organizationId}
              onChange={(event) => setOrganizationId(event.target.value)}
            >
              {session.organizations.map((item) => (
                <option value={item.id} key={item.id}>{item.name}</option>
              ))}
            </select>
          ) : (
            <span className="organization-name">{organization?.name}</span>
          )}
          <a href="https://api.terrasatch.com/portal" target="_blank" rel="noreferrer">
            Full workspace
          </a>
          <button className="ghost" onClick={signOut}>Sign out</button>
        </div>
      </header>

      <div className="app-grid">
        <aside className="context-rail">
          <div className="rail-section">
            <span className="eyebrow">SIGNED IN</span>
            <h2>{session.user?.name}</h2>
            <p>{session.user?.email}</p>
            <StatusPill tone="good">{organization?.role || "member"}</StatusPill>
          </div>

          <div className="rail-section">
            <span className="eyebrow">WORKSPACE</span>
            <div className="metric-grid">
              <div><strong>{records}</strong><span>records</span></div>
              <div><strong>{sites}</strong><span>sites</span></div>
              <div><strong>{connectedTools}</strong><span>tools</span></div>
              <div><strong>{pendingActions.length}</strong><span>reviews</span></div>
            </div>
          </div>

          <div className="rail-section">
            <span className="eyebrow">ACTIVE MODULES</span>
            <div className="tag-list">
              {(workspace?.modules || []).map((module) => (
                <span key={module}>{module}</span>
              ))}
              {!workspace?.modules?.length ? <p>No modules loaded yet.</p> : null}
            </div>
          </div>

          <button className="secondary full" onClick={() => loadWorkspace()} disabled={loadingWorkspace}>
            {loadingWorkspace ? "Refreshing…" : "Refresh context"}
          </button>
        </aside>

        <section className="conversation-panel">
          <div className="conversation-heading">
            <div>
              <span className="eyebrow">FIELD INTELLIGENCE</span>
              <h1>What needs your attention?</h1>
              <p>
                Ask Satchy about the field context available to {organization?.name || "your organization"}.
              </p>
            </div>
            <StatusPill tone={pendingActions.length ? "warn" : "good"}>
              {pendingActions.length ? `${pendingActions.length} awaiting review` : "No pending approvals"}
            </StatusPill>
          </div>

          <div className="conversation" aria-live="polite">
            {conversation.length === 0 ? (
              <div className="empty-state">
                <Image
                  src="https://api.terrasatch.com/assets/satchy.png"
                  width={58}
                  height={58}
                  alt=""
                />
                <h3>Satchy is connected.</h3>
                <p>
                  Start with a handoff, field summary, workflow question, or ask what has
                  changed in your current workspace.
                </p>
                <div className="suggestions">
                  {[
                    "Summarize my workspace.",
                    "What needs my attention?",
                    "What field context do we have right now?",
                  ].map((text) => (
                    <button key={text} onClick={() => setPrompt(text)}>{text}</button>
                  ))}
                </div>
              </div>
            ) : (
              conversation.map((item, index) => (
                <article className={`message message-${item.role}`} key={`${item.role}-${index}`}>
                  <span>{item.role === "assistant" ? "Satchy" : "You"}</span>
                  <p>{item.text}</p>
                  {item.approvalRequired ? (
                    <small>Approval required before the proposed action can execute.</small>
                  ) : null}
                </article>
              ))
            )}
          </div>

          {error ? <p className="error app-error" role="alert">{error}</p> : null}
          {status ? <p className="status" role="status">{status}</p> : null}

          <form className="composer" onSubmit={sendMessage}>
            <textarea
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              maxLength={4000}
              placeholder="Ask Satchy…"
              aria-label="Ask Satchy"
              required
            />
            <button className="primary" disabled={sending || !organizationId}>
              {sending ? "Working…" : "Send"}
            </button>
          </form>
        </section>

        <aside className="runs-rail">
          <div className="runs-heading">
            <div>
              <span className="eyebrow">RECENT</span>
              <h2>Satchy runs</h2>
            </div>
            <button className="icon-button" onClick={() => loadWorkspace()} aria-label="Refresh runs">
              ↻
            </button>
          </div>
          <div className="run-list">
            {runs.length ? runs.map((run) => (
              <article className="run-card" key={run.id}>
                <div>
                  <StatusPill tone={run.status === "completed" ? "good" : run.status === "failed" ? "bad" : "warn"}>
                    {run.status.replaceAll("_", " ")}
                  </StatusPill>
                  <time>{new Date(run.created_at).toLocaleString()}</time>
                </div>
                <p>{run.input_text}</p>
                {run.response_text ? <small>{run.response_text}</small> : null}
              </article>
            )) : (
              <p className="muted">No Satchy runs yet.</p>
            )}
          </div>
        </aside>
      </div>
    </main>
  );
}

export default function SatchyPage() {
  const [session, setSession] = useState(null);
  const [booting, setBooting] = useState(true);
  const [error, setError] = useState("");

  async function refreshSession() {
    setError("");
    try {
      const next = await client.workspaceSession();
      setSession(next);
      return next;
    } catch (err) {
      setError(messageFor(err));
      setSession(null);
      return null;
    } finally {
      setBooting(false);
    }
  }

  useEffect(() => {
    refreshSession();
  }, []);

  if (booting) {
    return (
      <main className="boot-screen">
        <Image
          src="https://api.terrasatch.com/assets/satchy.png"
          width={70}
          height={70}
          alt="Satchy"
          priority
        />
        <p>Connecting to TerraSatch…</p>
      </main>
    );
  }

  if (!session?.user) {
    return (
      <>
        <Login csrfToken={session?.csrf_token} onSignedIn={refreshSession} />
        {error ? <p className="floating-error">{error}</p> : null}
      </>
    );
  }

  return (
    <AppShell
      session={session}
      onRefreshSession={refreshSession}
      onSignedOut={() => refreshSession()}
    />
  );
}
