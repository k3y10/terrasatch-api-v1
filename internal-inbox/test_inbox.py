import base64
import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from svix.webhooks import Webhook

from app import create_app, password_hash


@pytest.fixture
def inbox(tmp_path):
    users = tmp_path / "users.json"
    users.write_text(json.dumps({"ops@terrasatch.com": {
        "password_hash": password_hash("fixture-password-only"),
        "mailboxes": ["ops@terrasatch.com"],
    }}))
    config = dict(database=str(tmp_path / "test.db"), users_file=str(users), secret="x" * 40,
                  origin="http://testserver", api_key="test-not-a-real-key", sending=False,
                  secure=False, daily_limit=1, monthly_limit=2,
                  webhook_secret="whsec_" + base64.b64encode(b"test-secret-only-32-bytes-00000000").decode())
    app = create_app(config)
    client = TestClient(app, headers={"Origin": config["origin"]})
    return app, client


def sign_in(client):
    assert client.post("/api/login", json={"username": "ops@terrasatch.com",
                       "password": "fixture-password-only"}).status_code == 200
    csrf = client.get("/api/session").json()["csrf"]
    client.headers["x-csrf-token"] = csrf


def draft(client, mailbox="ops@terrasatch.com"):
    return client.post("/api/drafts", json=dict(mailbox=mailbox, recipient="test@example.test",
                       subject="QA only", body="No real mail is sent by these tests."))


def test_unauthenticated_access_and_mailbox_isolation(inbox):
    _, client = inbox
    assert client.get("/api/messages?mailbox=ops@terrasatch.com").status_code == 401
    sign_in(client)
    assert client.get("/api/messages?mailbox=keaton@terrasatch.com").status_code == 403
    assert draft(client, "keaton@terrasatch.com").status_code == 403


def test_csrf_and_disabled_sending(inbox):
    _, client = inbox
    sign_in(client)
    saved = draft(client).json()["id"]
    assert client.post(f"/api/messages/{saved}/send").status_code == 503
    del client.headers["x-csrf-token"]
    assert draft(client).status_code == 403


def test_sending_is_once_and_hard_budget_is_enforced(inbox):
    app, client = inbox
    calls = []

    async def provider(method, path, **kwargs):
        calls.append(kwargs)
        return {"id": "provider-qa-1"}

    app.state.provider = provider
    app.state.config["sending"] = True
    sign_in(client)
    saved = draft(client).json()["id"]
    assert client.post(f"/api/messages/{saved}/send").status_code == 200
    assert client.post(f"/api/messages/{saved}/send").status_code == 200
    second = draft(client).json()["id"]
    assert client.post(f"/api/messages/{second}/send").status_code == 429
    assert len(calls) == 1
    assert calls[0]["headers"]["Idempotency-Key"] == saved


def test_uncertain_send_is_not_automatically_retried(inbox):
    app, client = inbox
    async def provider(*args, **kwargs):
        raise TimeoutError()
    app.state.provider = provider
    app.state.config["sending"] = True
    sign_in(client)
    saved = draft(client).json()["id"]
    assert client.post(f"/api/messages/{saved}/send").status_code == 502
    assert client.post(f"/api/messages/{saved}/send").status_code == 409


def test_verified_inbound_is_deduplicated_and_html_is_not_rendered(inbox):
    app, client = inbox
    calls = []
    async def provider(*args, **kwargs):
        calls.append(args)
        return {"from": "sender@example.test", "subject": "<script>bad</script>",
                "html": '<img src="https://tracking.example.test">', "text": None}
    app.state.provider = provider
    payload = json.dumps({"type": "email.received", "data": {
        "email_id": str(uuid4()), "to": ["ops@terrasatch.com", "unknown@terrasatch.com"]}})
    assert client.post("/webhooks/resend", content=payload).status_code == 400
    now = datetime.now(UTC)
    signature = Webhook(app.state.config["webhook_secret"]).sign("msg_test", now, payload)
    headers = {"svix-id": "msg_test", "svix-timestamp": str(int(now.timestamp())),
               "svix-signature": signature}
    assert client.post("/webhooks/resend", content=payload, headers=headers).status_code == 200
    assert client.post("/webhooks/resend", content=payload, headers=headers).json()["duplicate"]
    sign_in(client)
    rows = client.get("/api/messages?mailbox=ops@terrasatch.com").json()
    assert len(rows) == len(calls) == 1
    assert "https://tracking" not in rows[0]["body"]


def test_password_change_invalidates_existing_session(inbox):
    app, client = inbox
    sign_in(client)
    from pathlib import Path
    path = Path(app.state.config["users_file"])
    data = json.loads(path.read_text())
    data["ops@terrasatch.com"]["password_hash"] = password_hash("replacement-fixture-password")
    path.write_text(json.dumps(data))
    assert client.get("/api/session").status_code == 401


def test_login_rate_limit(inbox):
    _, client = inbox
    for _ in range(5):
        assert client.post("/api/login", json={"username": "unknown", "password": "bad"}).status_code == 401
    assert client.post("/api/login", json={"username": "unknown", "password": "bad"}).status_code == 429


def test_billing_relay_preserves_signed_payload_and_retries_failure(inbox, monkeypatch):
    import httpx
    app, client = inbox
    calls = []
    app.state.config['billing_webhook_url'] = 'https://api.terrasatch.com/api/v1/billing/resend/webhook'
    class Relay:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, url, **kwargs):
            calls.append((url, kwargs))
            return httpx.Response(200, request=httpx.Request('POST', url))
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kwargs: Relay())
    payload = json.dumps({'type': 'email.delivered', 'data': {'email_id': str(uuid4())}})
    now = datetime.now(UTC)
    headers = {'svix-id': 'msg_relay', 'svix-timestamp': str(int(now.timestamp())),
               'svix-signature': Webhook(app.state.config['webhook_secret']).sign('msg_relay', now, payload)}
    assert client.post('/webhooks/resend', content=payload, headers=headers).json() == {'relayed': True}
    assert calls[0][1]['content'] == payload.encode()
    assert calls[0][1]['headers']['svix-signature'] == headers['svix-signature']
    async def fail(self, *args, **kwargs): raise TimeoutError()
    monkeypatch.setattr(Relay, 'post', fail)
    assert client.post('/webhooks/resend', content=payload, headers=headers).status_code == 503
    app.state.config['billing_webhook_url'] = 'https://untrusted.example.test/'
    assert client.post('/webhooks/resend', content=payload, headers=headers).status_code == 503


def test_storage_and_request_limits(inbox):
    import sqlite3
    app, client = inbox
    assert client.post('/api/login', content='{}', headers={'content-length': 'bad'}).status_code == 400
    assert client.post('/api/login', content='{}', headers={'content-length': '262145'}).status_code == 413
    sign_in(client)
    with sqlite3.connect(app.state.config['database']) as c:
        c.executemany('INSERT INTO messages (id,mailbox,sender,recipient,subject,body,folder,created) VALUES (?,?,?,?,?,?,?,?)',
                      [(str(i), 'ops@terrasatch.com', 'fixture', 'fixture', 'fixture', 'fixture', 'draft', 0) for i in range(5000)])
    assert draft(client).status_code == 503
