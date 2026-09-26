"""Private, single-team inbox. Run separately from the public/customer API."""
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from email.utils import parseaddr
from pathlib import Path
from uuid import UUID, uuid4

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from itsdangerous import BadSignature, URLSafeTimedSerializer
from pydantic import BaseModel, Field
from svix.webhooks import Webhook

ROOT = Path(__file__).parent


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1)
    return salt + ":" + digest.hex()


class Draft(BaseModel):
    mailbox: str = Field(max_length=254)
    recipient: str = Field(max_length=254)
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=50000)


def create_app(config=None):
    cfg = config or {
        "database": os.getenv("INBOX_DATABASE", "/data/inbox.db"),
        "users_file": os.getenv("INBOX_USERS_FILE", "/data/users.json"),
        "secret": os.getenv("INBOX_SESSION_SECRET", ""),
        "origin": os.getenv("INBOX_ORIGIN", "https://mail.terrasatch.com"),
        "api_key": os.getenv("RESEND_API_KEY", ""),
        "webhook_secret": os.getenv("RESEND_WEBHOOK_SECRET", ""),
        "sending": os.getenv("INBOX_SENDING_ENABLED", "false") == "true",
        "secure": True,
        "daily_limit": int(os.getenv("INBOX_DAILY_SEND_LIMIT", "25")),
        "monthly_limit": int(os.getenv("INBOX_MONTHLY_SEND_LIMIT", "750")),
        "billing_webhook_url": os.getenv("INBOX_BILLING_WEBHOOK_URL", ""),
    }
    if len(cfg["secret"]) < 32:
        raise RuntimeError("Set a random INBOX_SESSION_SECRET of at least 32 characters")
    if not 1 <= cfg["daily_limit"] <= 100 or not 1 <= cfg["monthly_limit"] <= 3000:
        raise RuntimeError("Sending budgets must stay within free-tier ceilings")
    signer = URLSafeTimedSerializer(cfg["secret"], salt="terrasatch-internal-mail")
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.config = cfg

    @contextmanager
    def db():
        connection = sqlite3.connect(cfg["database"], timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    Path(cfg["database"]).parent.mkdir(parents=True, exist_ok=True)
    with db() as c:
        c.executescript("""
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS messages (
          id TEXT PRIMARY KEY, mailbox TEXT NOT NULL, sender TEXT NOT NULL,
          recipient TEXT NOT NULL, subject TEXT NOT NULL, body TEXT NOT NULL,
          folder TEXT NOT NULL, created REAL NOT NULL, provider_id TEXT,
          attempted REAL, actor TEXT, UNIQUE(mailbox,provider_id));
        CREATE TABLE IF NOT EXISTS attempts (ip TEXT, created REAL);
        CREATE TABLE IF NOT EXISTS audit (actor TEXT, action TEXT, message_id TEXT, created REAL);
        """)

    def users():
        return json.loads(Path(cfg["users_file"]).read_text())

    def identity(request, mutate=False):
        try:
            session = signer.loads(request.cookies.get("inbox_session", ""), max_age=43200)
            user = users()[session["user"]]
            if not hmac.compare_digest(session["version"], user["password_hash"][-32:]):
                raise ValueError()
        except (BadSignature, KeyError, ValueError):
            raise HTTPException(401, "Sign in to your internal inbox") from None
        if mutate and (
            request.headers.get("origin") != cfg["origin"]
            or not hmac.compare_digest(request.headers.get("x-csrf-token", ""), session["csrf"])
        ):
            raise HTTPException(403, "Refresh the inbox and try again")
        return session, user

    def permitted(user, mailbox):
        if mailbox not in user["mailboxes"]:
            raise HTTPException(403, "Mailbox access denied")

    async def provider(method, path, **kwargs):
        if not cfg["api_key"]:
            raise HTTPException(503, "Email provider is not connected")
        headers = {"Authorization": "Bearer " + cfg["api_key"]}
        headers.update(kwargs.pop("headers", {}))
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.request(method, "https://api.resend.com" + path,
                                            headers=headers, **kwargs)
            response.raise_for_status()
            return response.json()

    app.state.provider = provider

    @app.middleware("http")
    async def security(request, call_next):
        try:
            length = int(request.headers.get("content-length", "0"))
        except ValueError:
            return JSONResponse({"detail": "Invalid content length"}, status_code=400)
        if length < 0 or length > 262144:
            return JSONResponse({"detail": "Request too large"}, status_code=413)
        response = await call_next(request)
        response.headers.update({
            "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer", "X-Frame-Options": "DENY",
            "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; "
                                       "img-src 'self'; frame-ancestors 'none'; base-uri 'none'",
        })
        return response

    @app.get("/")
    async def index():
        return FileResponse(ROOT / "static/index.html")

    @app.get("/assets/{name}")
    async def asset(name: str):
        if name not in {"app.js", "style.css", "satchy.png", "barlow.ttf", "rajdhani.ttf", "jetbrains-mono.ttf"}:
            raise HTTPException(404)
        return FileResponse(ROOT / "static" / name)

    @app.post("/api/login")
    async def login(request: Request):
        if request.headers.get("origin") != cfg["origin"]:
            raise HTTPException(403)
        payload = await request.json()
        username = str(payload.get("username", "")).lower().strip()
        password = str(payload.get("password", ""))
        if len(password) > 1024:
            raise HTTPException(400)
        ip, now = request.client.host, time.time()
        with db() as c:
            c.execute("BEGIN IMMEDIATE")
            c.execute("DELETE FROM attempts WHERE created < ?", (now - 900,))
            if c.execute("SELECT count(*) FROM attempts WHERE ip=?", (ip,)).fetchone()[0] >= 5:
                raise HTTPException(429, "Too many attempts. Try again in 15 minutes.")
            c.execute("INSERT INTO attempts VALUES (?,?)", (ip, now))
        user = users().get(username)
        stored = user["password_hash"] if user else password_hash("invalid-account-password")
        if not hmac.compare_digest(password_hash(password, stored.split(":")[0]), stored) or not user:
            raise HTTPException(401, "Email or password is incorrect")
        token = signer.dumps({"user": username, "csrf": secrets.token_urlsafe(32),
                              "version": stored[-32:]})
        response = JSONResponse({"ok": True})
        response.set_cookie("inbox_session", token, httponly=True, secure=cfg["secure"],
                            samesite="strict", max_age=43200)
        return response

    @app.post("/api/logout")
    async def logout(request: Request):
        identity(request, True)
        response = JSONResponse({"ok": True})
        response.delete_cookie("inbox_session")
        return response

    @app.get("/api/session")
    async def session(request: Request):
        session, user = identity(request)
        return {"user": session["user"], "mailboxes": user["mailboxes"], "csrf": session["csrf"],
                "sending_enabled": bool(cfg["sending"] and cfg["api_key"]),
                "daily_limit": cfg["daily_limit"], "monthly_limit": cfg["monthly_limit"]}

    @app.get("/api/messages")
    async def messages(request: Request, mailbox: str, folder: str = "inbox"):
        _, user = identity(request)
        permitted(user, mailbox)
        if folder not in {"inbox", "sent", "draft", "pending"}:
            raise HTTPException(400)
        with db() as c:
            rows = c.execute("SELECT * FROM messages WHERE mailbox=? AND folder=? "
                             "ORDER BY created DESC LIMIT 100", (mailbox, folder)).fetchall()
        return [dict(row) for row in rows]

    @app.post("/api/drafts")
    async def draft(request: Request, payload: Draft):
        session, user = identity(request, True)
        permitted(user, payload.mailbox)
        if not re.fullmatch(r"[^\s<>@]+@[^\s<>@]+\.[^\s<>@]+", payload.recipient):
            raise HTTPException(400, "Enter one valid recipient email")
        if "\n" in payload.subject or "\r" in payload.subject:
            raise HTTPException(400, "Subject must be one line")
        key = str(uuid4())
        with db() as c:
            c.execute("BEGIN IMMEDIATE")
            if c.execute("SELECT count(*) FROM messages").fetchone()[0] >= 5000:
                raise HTTPException(503, "Inbox storage budget reached; contact your administrator")
            c.execute("INSERT INTO messages (id,mailbox,sender,recipient,subject,body,folder,created,actor) "
                      "VALUES (?,?,?,?,?,?, 'draft',?,?)", (key, payload.mailbox, payload.mailbox,
                      payload.recipient, payload.subject, payload.body, time.time(), session["user"]))
        return {"id": key}

    @app.post("/api/messages/{key}/send")
    async def send(key: str, request: Request):
        session, user = identity(request, True)
        if not cfg["sending"] or not cfg["api_key"]:
            raise HTTPException(503, "Sending is disabled until provider setup is verified")
        now = time.time()
        with db() as c:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute("SELECT * FROM messages WHERE id=?", (key,)).fetchone()
            if not row:
                raise HTTPException(404)
            permitted(user, row["mailbox"])
            if row["folder"] == "sent":
                return {"status": "sent"}
            if row["folder"] != "draft":
                raise HTTPException(409, "Send is awaiting reconciliation. Do not create a duplicate.")
            for window, limit in [(86400, cfg["daily_limit"]), (31 * 86400, cfg["monthly_limit"])]:
                count = c.execute("SELECT count(*) FROM messages WHERE attempted>?", (now-window,)).fetchone()[0]
                if count >= limit:
                    raise HTTPException(429, "Internal sending budget reached; no paid overage attempted")
            c.execute("UPDATE messages SET folder='pending',attempted=? WHERE id=?", (now, key))
        try:
            result = await app.state.provider("POST", "/emails", headers={"Idempotency-Key": key},
                json={"from": row["mailbox"], "to": [row["recipient"]], "subject": row["subject"],
                      "text": row["body"]})
            if not result.get("id"):
                raise ValueError("Missing provider receipt")
        except Exception:
            raise HTTPException(502, "Send outcome needs reconciliation in Resend; message remains pending") from None
        with db() as c:
            c.execute("UPDATE messages SET folder='sent',provider_id=? WHERE id=?", (result["id"], key))
            c.execute("INSERT INTO audit VALUES (?,?,?,?)", (session["user"], "send", key, now))
        return {"status": "sent"}

    @app.post("/webhooks/resend")
    async def receive(request: Request):
        if not cfg["webhook_secret"]:
            raise HTTPException(503, "Receiving is not configured")
        raw = await request.body()
        if len(raw) > 262144:
            raise HTTPException(413)
        try:
            event = Webhook(cfg["webhook_secret"]).verify(raw, dict(request.headers))
        except Exception:
            raise HTTPException(400, "Invalid webhook signature") from None
        if event.get("type") != "email.received":
            relay = cfg.get("billing_webhook_url")
            if relay:
                if relay not in {
                    "https://staging-api.terrasatch.com/api/v1/workspace/billing/resend/webhook",
                    "https://api.terrasatch.com/api/v1/billing/resend/webhook",
                }:
                    raise HTTPException(503, "Billing webhook destination is not allowed")
                try:
                    headers = {k: v for k, v in request.headers.items() if k.startswith("svix-")}
                    headers["Content-Type"] = "application/json"
                    async with httpx.AsyncClient(timeout=15) as client:
                        result = await client.post(relay, content=raw, headers=headers)
                        result.raise_for_status()
                except Exception:
                    raise HTTPException(503, "Billing delivery event relay needs retry") from None
                return {"relayed": True}
            return {"ignored": True}
        try:
            email_id = str(UUID(event["data"]["email_id"]))
        except (ValueError, KeyError, TypeError):
            raise HTTPException(400) from None
        known = {m for user in users().values() for m in user["mailboxes"]}
        recipients = {parseaddr(x)[1].lower() for x in event["data"].get("to", [])} & known
        if not recipients:
            return {"ignored": True}
        with db() as c:
            recipients = {m for m in recipients if not c.execute(
                "SELECT id FROM messages WHERE mailbox=? AND provider_id=?", (m, email_id)
            ).fetchone()}
            if not recipients:
                return {"duplicate": True}
            if c.execute("SELECT count(*) FROM messages").fetchone()[0] >= 5000:
                raise HTTPException(503, "Inbox storage budget reached; archive before retrying")
        try:
            mail = await app.state.provider("GET", "/emails/receiving/" + email_id)
        except Exception:
            raise HTTPException(503, "Retry receiving later") from None
        body = mail.get("text") or "This email has no plain-text body. View it in Resend."
        # No remote images, HTML execution, or automatic attachments in the private inbox.
        if mail.get("attachments"):
            body += "\n\nAttachments are available in Resend; not downloaded here."
        with db() as c:
            c.execute("BEGIN IMMEDIATE")
            if c.execute("SELECT count(*) FROM messages").fetchone()[0] + len(recipients) > 5000:
                raise HTTPException(503, "Inbox storage budget reached; contact your administrator")
            for mailbox in recipients:
                c.execute("INSERT OR IGNORE INTO messages (id,mailbox,sender,recipient,subject,body,"
                          "folder,created,provider_id) VALUES (?,?,?,?,?,?,'inbox',?,?)",
                          (str(uuid4()), mailbox, str(mail.get("from", ""))[:500], mailbox,
                           str(mail.get("subject", "(No subject)"))[:200], body[:100000], time.time(), email_id))
        return {"ok": True}

    return app
