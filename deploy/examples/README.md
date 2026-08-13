# Production Deployment: `api.terrasatch.com`

This deployment model runs the TerraSatch API and worker under systemd, with Caddy
terminating HTTPS and WSS. It is intentionally provider-neutral: managed PostgreSQL
and Redis or self-hosted instances are both supported.

## Prerequisites

1. Provision a Linux host with Python 3.12+, `uv`, Caddy, PostgreSQL access, and
   Redis access.
2. Point the public DNS `A`/`AAAA` record for `api.terrasatch.com` at the host.
3. Allow inbound TCP `80` and `443`. Keep `8000`, PostgreSQL, and Redis private.
4. Clone this standalone repository to `/opt/terrasatch-ai-radio-core` as the
   `terrasatch` service user.
5. Install the systemd units from `deploy/systemd/` and the Caddy configuration
   from `deploy/examples/Caddyfile`.

## Secret configuration

```bash
sudo install -d -m 0750 -o terrasatch -g terrasatch /etc/terrasatch
sudo install -m 0600 -o terrasatch -g terrasatch \
  deploy/examples/production.env.example /etc/terrasatch/api.env
```

Replace every placeholder in `/etc/terrasatch/api.env`. Configure browser
administration using a generated scrypt hash and session secret; do not place a raw
password or API key in that file. On the secured server, run the interactive
bootstrap command as the service user to update that file without printing the
password or generated session secret:

```bash
sudo -u terrasatch /opt/terrasatch-ai-radio-core/.venv/bin/terrasatch \
  admin configure --env-file /etc/terrasatch/api.env
```

The admin URL is `https://api.terrasatch.com/admin`.

## Startup and verification

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now terrasatch-api terrasatch-worker
sudo systemctl reload caddy

curl --fail --show-error https://api.terrasatch.com/health/ready
terrasatch deployment check --base-url https://api.terrasatch.com --json
curl --fail --show-error https://api.terrasatch.com/api/v1/reference
```

`/health` checks only process liveness. `/health/ready` checks PostgreSQL and
Redis and returns `503` on failure. `/api/v1/admin/quality` additionally checks
the worker heartbeat and requires an `admin`-scoped bearer key. The browser console
shows that same quality report after administrator login.

## API and administrative boundaries

- Public: `GET /health`, `GET /health/live`, `GET /health/ready`,
  `GET /api/v1/health`, and `GET /api/v1/reference`.
- Server integration: bearer API keys are required for `GET /api/v1/auth/me` and
  admin-scoped keys are required for `GET /api/v1/admin/quality`, `GET`/`POST`
  `/api/v1/sites`, `GET`/`POST` `/api/v1/api-keys`, and
  `POST /api/v1/api-keys/{api_key_id}/revoke`. All tenant ownership comes from
  the presented API key, never from a request-provided organization ID.
- Browser administration: `/admin` uses a separate password-backed signed session
  with CSRF protection. It supports only explicit organization, site, and API-key
  creation. It intentionally cannot run arbitrary shell or radio commands.

## Updates and rollback

```bash
cd /opt/terrasatch-ai-radio-core
git pull --ff-only
uv sync --frozen --no-dev
sudo systemctl restart terrasatch-api terrasatch-worker
terrasatch deployment check --base-url https://api.terrasatch.com
```

The API unit runs `alembic upgrade head` before starting. Back up PostgreSQL before
introducing a migration that cannot be reversed safely.