# TerraSatch API

TerraSatch API is the standalone backend for TerraSatch field intelligence and TerraListen
software radio workflows. It accepts authorized operational input, preserves source records,
extracts structured operational events, persists them in PostgreSQL, and exposes tenant-scoped
REST and realtime WebSocket interfaces for independent TerraSatch demos and partner applications.

Production: `https://api.terrasatch.com`

This repository owns the backend pipeline. TerraSatch websites, focused demos, and partner pilots
remain separate clients of this service.

## What works now

The current software path is:

```text
Authorized text/radio-style input
  → Transmission
  → Transcript
  → provider-neutral TerraEngine
  → OperationalEvent
  → PostgreSQL
  → Redis event publication
  → REST + authenticated WebSocket clients
```

Implemented platform capabilities include:

- FastAPI / OpenAPI backend
- PostgreSQL persistence and Alembic migrations
- Redis readiness, worker heartbeat, and event publication
- organizations, sites, teams, service API keys, and browser administration
- tenant-derived bearer authorization and scope enforcement
- agents, logical channels, and callsigns
- idempotent transmission ingestion using tenant + `source_message_id`
- immutable source transmissions and transcripts
- source-linked structured operational events
- deterministic/offline TerraEngine provider behind an `IntelligenceProvider` protocol
- tenant-safe list/detail endpoints and filters
- authenticated tenant-scoped WebSocket subscriptions
- software radio simulator using the same persistence/intelligence path as API ingestion
- Docker/Compose deployment behind Caddy at `api.terrasatch.com`

The current implementation does **not** yet perform WAV/microphone speech recognition, receive
RTL-SDR/Nooelec audio, run an Edge Agent, deliver production webhooks, expose a TypeScript SDK,
or implement billing/retention/audit automation. Those remain later phases.

See [PROJECT_CHECKLIST.md](PROJECT_CHECKLIST.md) for the exact phase status.

## Core API resources

Public operational checks:

```text
GET /health
GET /health/live
GET /health/ready
GET /api/v1/health
GET /api/v1/reference
GET /openapi.json
```

Authenticated identity/control plane:

```text
GET   /api/v1/auth/me

GET   /api/v1/sites
POST  /api/v1/sites
GET   /api/v1/sites/{site_id}
PATCH /api/v1/sites/{site_id}

GET   /api/v1/teams
POST  /api/v1/teams
GET   /api/v1/teams/{team_id}
PATCH /api/v1/teams/{team_id}

GET   /api/v1/api-keys
POST  /api/v1/api-keys
POST  /api/v1/api-keys/{api_key_id}/revoke
```

Radio/intelligence configuration:

```text
GET   /api/v1/agents
POST  /api/v1/agents
GET   /api/v1/agents/{agent_id}
PATCH /api/v1/agents/{agent_id}

GET   /api/v1/channels
POST  /api/v1/channels
GET   /api/v1/channels/{channel_id}
PATCH /api/v1/channels/{channel_id}

GET   /api/v1/callsigns
POST  /api/v1/callsigns
GET   /api/v1/callsigns/{callsign_id}
PATCH /api/v1/callsigns/{callsign_id}
```

Source and intelligence records:

```text
POST /api/v1/transmissions
GET  /api/v1/transmissions
GET  /api/v1/transmissions/{transmission_id}

GET /api/v1/transcripts
GET /api/v1/transcripts/{transcript_id}

GET /api/v1/events
GET /api/v1/events/{event_id}
```

Realtime:

```text
WSS /ws/v1/events
```

The first WebSocket message authenticates and subscribes without placing the service token in the
URL:

```json
{
  "action": "subscribe",
  "token": "<service-api-key>",
  "topics": ["events", "transmissions", "transcripts"]
}
```

## API authentication and scopes

HTTP integrations send:

```http
Authorization: Bearer <service-api-key>
```

The organization boundary comes from the credential stored by the server; clients do not choose
or override their tenant with an `organization_id` header or request field.

`admin` remains the tenant-local wildcard scope. More focused integrations can use:

```text
read:sites       write:sites
read:teams       write:teams
read:agents      write:agents
read:channels    write:channels
read:callsigns   write:callsigns
edge:ingest
read:transmissions
read:transcripts
read:events
```

For compatibility with credentials issued before the focused configuration scopes were added,
`read:events` can still read agents/channels/callsigns and `write:agents` can still manage
callsigns. New integrations should use the focused scopes.

## Transmission ingestion

A software client or future Edge Agent submits one authorized message through:

```http
POST /api/v1/transmissions
Authorization: Bearer <key-with-edge:ingest>
Content-Type: application/json
```

Example:

```json
{
  "site_id": "00000000-0000-0000-0000-000000000000",
  "agent_id": null,
  "channel_id": null,
  "callsign": "Patrol 4",
  "text": "Wind loading is visible near the ridgeline on the east aspect around 9800 feet.",
  "source": "demo",
  "source_message_id": "demo-message-001"
}
```

The API persists the source `Transmission`, then a `Transcript`, then one or more structured
`OperationalEvent` records. Repeating the same `source_message_id` within the same organization
returns the previously persisted records instead of generating duplicates.

## Useful filters

Configuration and history endpoints accept focused query filters so demos do not need to download
an entire tenant history. Examples include:

```text
GET /api/v1/sites?enabled=true
GET /api/v1/teams?site_id=<uuid>&enabled=true
GET /api/v1/agents?site_id=<uuid>&profile=ski_patrol&enabled=true
GET /api/v1/channels?site_id=<uuid>&agent_id=<uuid>
GET /api/v1/callsigns?site_id=<uuid>&team_id=<uuid>&enabled=true
GET /api/v1/transmissions?site_id=<uuid>&channel_id=<uuid>&source=simulator
GET /api/v1/transcripts?transmission_id=<uuid>
GET /api/v1/events?site_id=<uuid>&event_type=WEATHER&callsign=Patrol%204
```

## Software simulator

The simulator is a software acceptance tool, not a separate fake intelligence system. It feeds the
same `ingest_transmission` service used by the REST endpoint.

```bash
terrasatch org create "TerraSatch Demo"
terrasatch site create "Wasatch Demo" --organization "TerraSatch Demo"
terrasatch callsign add --name "Patrol 4" --organization "TerraSatch Demo"
terrasatch agent create --name "demo-agent" --profile ski_patrol \
  --organization "TerraSatch Demo" --site "Wasatch Demo"
terrasatch simulate radio --organization "TerraSatch Demo" --site "Wasatch Demo"
terrasatch event list --organization "TerraSatch Demo"
```

Inspect one event with:

```bash
terrasatch event show <event-uuid> --organization "TerraSatch Demo" --json
```

The same records must then be visible through authenticated `GET /api/v1/events` and the realtime
WebSocket event topic.

## Development setup

Requirements:

- Python 3.12+
- Docker / Docker Compose
- `uv`

Setup:

```bash
git clone <repository-url> terrasatch-ai-radio-core
cd terrasatch-ai-radio-core
cp .env.example .env
docker compose up -d postgres redis
uv sync --extra dev
uv run alembic upgrade head
```

Run the API and worker:

```bash
uv run terrasatch serve
uv run terrasatch worker
```

Run checks:

```bash
uv run ruff check src tests
uv run pytest
```

## Browser administration

Browser administration is disabled until the admin environment values are configured. Run:

```bash
terrasatch admin configure
```

The environment writer safely quotes Compose-sensitive values such as `$`-containing scrypt
password hashes. Restart the API and use HTTPS in production:

```text
https://api.terrasatch.com/admin
```

The browser console manages organizations/sites/API keys and quality information. It does not
execute arbitrary shell commands or transmit radio traffic.

## Oracle production deployment

The production topology is:

```text
api.terrasatch.com
  → Oracle public IP
  → Caddy :443
  → FastAPI 127.0.0.1:8000
  → PostgreSQL + Redis on private/loopback Docker networking
```

For an ordinary code release after merging to `main`:

```bash
cd /opt/terrasatch/api
git status -sb
git checkout main
git pull --ff-only origin main

docker compose config >/dev/null
docker compose build api worker
docker compose up -d --force-recreate api worker

docker compose ps
curl --fail http://127.0.0.1:8000/health/ready
curl --fail https://api.terrasatch.com/health/ready
```

When a release contains a new Alembic migration, run this after the build and before recreating the
long-running containers:

```bash
docker compose run --rm api alembic upgrade head
```

Migration `0004_radio_event_pipeline` introduces the current radio/event schema. A branding-only or
API-route-only update after that migration does not require another Alembic command.

Detailed deployment examples remain under [deploy/examples/README.md](deploy/examples/README.md).

## Security and radio safety

TerraSatch is receive-side decision support. The system must not invoke push-to-talk, transmit on
field radio channels, impersonate dispatch, or make autonomous life-safety decisions. Operators are
responsible for receiving and processing only traffic they are legally authorized to access.

Secrets belong in environment variables or ignored owner-only `.env` files and must never be
committed. Raw service API tokens are returned only when issued; stored credentials are hashed.

## Hardware status

Physical audio/radio ingestion is a later phase. Planned work includes WAV/microphone input,
SpeechToTextProvider implementations, `rtl_test`/`rtl_fm` receive adapters, Nooelec/RTL-SDR device
diagnostics, and a durable outbound Edge Agent. The software simulator exists specifically so the
canonical backend pipeline can be validated before those hardware dependencies are introduced.

## License

Proprietary. All rights reserved.
