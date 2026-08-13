# TerraSatch API

TerraSatch API is a deployable field-intelligence backend that transforms authorized
operational radio traffic into structured, searchable, real-time operational
intelligence. It exposes a stable REST, WebSocket, and webhook contract for
independent TerraSatch and partner applications.

The public production service is `https://api.terrasatch.com`. This repository is
the platform implementation; the repository name is never part of a public API path.

## Repository isolation

This is a standalone Git repository. It must not be placed inside or modify an
existing TerraSatch website, demo, frontend, relay, or prototype. External clients
consume the API; they do not own the radio intelligence pipeline.

## Current implementation status

The Phase 1 foundation is in active implementation. It provides configuration,
structured logging, health architecture, a FastAPI application, a Typer operations
CLI, PostgreSQL and Redis integration, Docker development services, and test
scaffolding. Subsequent phases are tracked in [PROJECT_CHECKLIST.md](PROJECT_CHECKLIST.md).

## Planned architecture

```text
Authorized radio/audio input
  -> input plugins
  -> audio/transcription pipeline
  -> TerraEngine
  -> structured events and context
  -> PostgreSQL and realtime event bus
  -> REST, WebSocket, and webhook clients
```

The platform is intentionally a modular monolith: the API, worker, data layer, and
replaceable providers live in one operable repository while retaining explicit
internal boundaries.

## Requirements

- Linux or another Docker-capable host
- Python 3.12 or newer for local development
- Docker Compose for PostgreSQL and Redis
- `uv` is the preferred Python package manager (installation instructions will be
  completed with the setup command)

## Development setup

These commands are the intended workflow once Phase 1 is complete:

```bash
git clone <repository-url> terrasatch-ai-radio-core
cd terrasatch-ai-radio-core
cp .env.example .env
docker compose up -d postgres redis
uv sync --extra dev
uv run alembic upgrade head
uv run terrasatch setup
uv run terrasatch serve
```

In another terminal:

```bash
uv run terrasatch worker
```

Run checks with:

```bash
uv run ruff check src tests
uv run pytest
```

## Admin Console And API Checks

The default local stack binds all services to `127.0.0.1`; it is reachable only
from this computer. Start or update it with:

```bash
docker compose up -d --build
curl --fail http://localhost:8000/health/ready
```

Public health checks are intentionally available without credentials:

```bash
curl --fail http://localhost:8000/health/ready
curl http://localhost:8000/api/v1/reference
```

The local API accepts browser requests from the usual development ports `3000`
and `4173`; configure the frontend's API base URL as `http://127.0.0.1:8000`.

To open the API to devices on a trusted local network for a temporary preview,
start Compose with your computer's LAN IP. It exposes only the API; PostgreSQL
and Redis stay private.

```bash
TERRASATCH_API_BIND_ADDRESS=0.0.0.0 \
TERRASATCH_LAN_HOST=192.168.1.25 \
docker compose up -d --build
```

The preview endpoint is then `http://192.168.1.25:8000`. Do not use this mode on
an untrusted network or directly expose it to the public internet. Use the Caddy
and systemd deployment path when you are ready for a preview or production cloud
host.

### Public `api.terrasatch.com` From This Computer

For a no-cost, public preview from this computer, use the optional Cloudflare
Tunnel Compose profile. It makes an outbound encrypted connection to Cloudflare,
so no router port-forwarding, public IP address, or inbound access to `8000`,
PostgreSQL, or Redis is needed. This is suitable while the computer and Docker
Desktop remain running; it is not an always-on production host.

1. Add `terrasatch.com` to Cloudflare DNS if it is not already there and update
  the registrar nameservers. In Cloudflare Zero Trust, create a remotely managed
  tunnel using the Docker connector.
2. Add the public hostname `api.terrasatch.com` to that tunnel and set its service
  to `http://api:8000`. Cloudflare creates the DNS route for the tunnel. Remove
  the old `api.terrasatch.com` CNAME to `terrasatch.com`/Vercel; it cannot serve
  this API.
3. Create an untracked `.env` file from `.env.example` and set the public URL,
  website origins, and the tunnel token. Do not commit the token.

```dotenv
TERRASATCH_ENV=production
TERRASATCH_DEPLOYMENT_NAME=cloudflare-tunnel
TERRASATCH_API_BASE_URL=https://api.terrasatch.com
TERRASATCH_CORS_ORIGINS=https://terrasatch.com,https://www.terrasatch.com
CLOUDFLARE_TUNNEL_TOKEN=<paste-the-token-from-cloudflare-here>
```

4. Start the private stack and the tunnel:

```bash
docker compose --profile public-tunnel up -d --build
docker compose ps
curl --fail --show-error https://api.terrasatch.com/health/ready
```

Cloudflare terminates HTTPS and securely supports WebSockets to the API. Keep
browser administration configured only with a strong local secret and use
`https://api.terrasatch.com/admin` only for authorized operators.

`/api/v1/reference` lists the GET and POST operations implemented by the running
release plus common HTTP/error responses. The public production health command is:

```bash
terrasatch deployment check --base-url https://api.terrasatch.com --json
```

Browser administration is disabled by default. For a local secured operator
session, run `terrasatch admin configure`, restart the API, and open
`http://localhost:8000/admin`. It provides quality reporting, organization and
site creation, and controlled API-key issuance. It deliberately does not execute
arbitrary terminal or radio commands from a browser.

For a complete production deployment to `https://api.terrasatch.com`, including
DNS, Caddy HTTPS/WSS termination, systemd, and secret handling, read
[deploy/examples/README.md](deploy/examples/README.md).

## Security and radio safety

TerraSatch is receive-only. The radio integration must never transmit, invoke
push-to-talk, issue operational commands, or make autonomous life-safety decisions.
Operators are responsible for receiving and processing only traffic they are legally
authorized to access. Secrets belong in environment variables or untracked `.env`
files and must never be committed.

## Hardware status

The planned RTL-SDR integration will use established Linux tools such as `rtl_test`
and `rtl_fm`; it will report unavailable drivers, permissions, and capture tools
explicitly. Physical BCA/Nooelec acceptance testing remains blocked until hardware
is connected and an authorized test frequency is configured.

## API contract

Versioned endpoints live under `/api/v1`; `/openapi.json` is a product contract.
Production documentation exposure is configuration-controlled. The target realtime
endpoint is `/ws/v1/events` over WSS in production.

## License

Proprietary. All rights reserved.