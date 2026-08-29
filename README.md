# TerraSatch API

TerraSatch API is the production backend for TerraSatch field intelligence and TerraListen radio workflows. It accepts authorized operational input, preserves source records, extracts structured events, persists them in PostgreSQL, publishes realtime updates through Redis, and exposes tenant-scoped REST/WebSocket interfaces for TerraSatch demos, partner applications, and paired Edge nodes.

Production: `https://api.terrasatch.com`

API release: **0.2.1**

## Current canonical path

```text
Simulator / reviewed Edge text / future STT
  → Transmission
  → Transcript
  → provider-neutral TerraEngine
  → OperationalEvent
  → PostgreSQL
  → Redis event publication
  → REST + authenticated WebSocket clients
```

Do not build a separate demo-only intelligence path. Simulator, recorded audio, live audio, SDR input, and Edge must converge on this same pipeline.

## Implemented platform capabilities

- FastAPI / OpenAPI backend
- PostgreSQL persistence and Alembic migrations
- Redis readiness, worker heartbeat, and event publication
- organizations, sites, teams, users, memberships, service API keys, and browser administration
- tenant-derived bearer authorization and scope enforcement
- agents, logical channels, callsigns, transmissions, transcripts, and operational events
- idempotent transmission ingestion using tenant + `source_message_id`
- provider-neutral TerraEngine with deterministic structured extraction
- authenticated tenant-scoped WebSocket subscriptions
- browser-based Edge pairing and tenant/site assignment
- Edge device registry, site-bound credentials, aggregated receiver telemetry, inventory, and remote configuration
- live registered Edge fleet health and provider-aware RX/TX capability state
- Satchy AI-channel configuration stored as Edge remote policy
- organization member portal with tenant-scoped fleet visibility
- public privacy-safe TerraSatch Network totals for registered/online nodes, field sites, members, and configured capacity
- configurable registration guardrails that pause new Edge/member registration without interrupting existing users or nodes
- Docker/Compose deployment behind Caddy at `api.terrasatch.com`

The dedicated field runtime lives in the separate `terrasatch-edge` repository. Its vNext radio
service keeps receive, local validation/transcription, and durable API delivery independent while
preserving the established single-call demo. This API stores meaningful transmissions plus
structured RF provenance; raw/rejected audio remains an Edge concern and is never persisted here.

See [PROJECT_CHECKLIST.md](PROJECT_CHECKLIST.md) for the current roadmap and validation state.

## Public operational checks

```text
GET /health
GET /health/live
GET /health/ready
GET /api/v1/health
GET /api/v1/network/status
GET /api/v1/reference
GET /openapi.json
```

`GET /api/v1/network/status` exposes aggregate counts only. It does not return organization names, device IDs, hardware inventories, callsigns, site names, or individual user records. The result is short-lived cached so the public landing page does not query PostgreSQL on every visual refresh.

## Network capacity guardrails

The default release limits are configurable through environment settings:

```text
TERRASATCH_MAX_EDGE_DEVICES=100
TERRASATCH_MAX_PORTAL_USERS=250
```

When a limit is reached, new registrations are paused while existing Edge heartbeats, ingestion, and portal access continue normally. Existing members can still have passwords/roles updated without consuming another unique-user slot.

Public capacity states are:

```text
0–79%     HEALTHY
80–89%    CAPACITY WATCH
90–99%    NEAR CAPACITY
100%      REGISTRATION PAUSED
```

These are onboarding guardrails, not a substitute for request throttling, queue/backpressure controls, or production capacity testing.

## Authenticated control plane

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

## Edge control plane

```text
POST  /api/v1/edge/pairings
POST  /api/v1/edge/pairings/token
POST  /api/v1/edge/pairings/{user_code}/approve
GET   /api/v1/edge/devices
PATCH /api/v1/edge/devices/{device_id}
GET   /api/v1/edge/me
POST  /api/v1/edge/heartbeat
GET   /api/v1/edge/config
```

A paired Edge credential currently receives `edge:connect`, `edge:ingest`, and `read:sites`. The raw device credential is returned once; only its hash remains stored by the API.

## Radio/intelligence resources

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

POST /api/v1/transmissions
GET  /api/v1/transmissions
GET  /api/v1/transmissions/{transmission_id}
GET  /api/v1/transcripts
GET  /api/v1/transcripts/{transcript_id}
GET  /api/v1/events
GET  /api/v1/events/{event_id}
```

Realtime:

```text
WSS /ws/v1/events
```

The first WebSocket message authenticates and subscribes without putting the service token in the URL:

```json
{
  "action": "subscribe",
  "token": "<service-api-key>",
  "topics": ["events", "transmissions", "transcripts"]
}
```

## Authentication and scopes

HTTP integrations send:

```http
Authorization: Bearer <service-api-key>
```

Tenant identity is always derived from the stored credential. Clients do not choose or override an organization through a request header.

Common scopes include:

```text
read:sites       write:sites
read:teams       write:teams
read:agents      write:agents
read:channels    write:channels
read:callsigns   write:callsigns
edge:connect     edge:ingest
read:edge        write:edge
read:transmissions
read:transcripts
read:events
```

`admin` remains the tenant-local wildcard scope.

## Browser surfaces

```text
/admin            TerraSatch superadmin operations console
/admin/members    organization member and role management
/portal/login     organization-user sign in
/portal           tenant-scoped organization fleet portal
```

The organization portal is intentionally observation-first. High-risk tenant configuration and radio policy remain in the superadmin surface.

## Transmission ingestion

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
  "source": "terrasatch-edge",
  "source_message_id": "edge-example-001"
}
```

The API persists a source `Transmission`, a `Transcript`, and structured `OperationalEvent` records. Reusing the same `source_message_id` within the same organization returns the existing result rather than creating duplicates.

## Development

Requirements:

- Python 3.12+
- Docker / Docker Compose
- `uv`

```bash
git clone <repository-url> terrasatch-api
cd terrasatch-api
cp .env.example .env
docker compose up -d postgres redis
uv sync --extra dev
uv run alembic upgrade head
uv run ruff check src tests
uv run pytest
```

Run the API and worker:

```bash
uv run terrasatch serve
uv run terrasatch worker
```

## Oracle production deployment

Production topology:

```text
api.terrasatch.com
  → Oracle public IP
  → Caddy :443
  → FastAPI 127.0.0.1:8000
  → PostgreSQL + Redis on private/loopback Docker networking
```

After merging a release to `main`, use the release script:

```bash
cd /opt/terrasatch/api
bash deploy/release-oracle.sh
```

The release script refuses a dirty working tree, updates `main`, validates Compose, builds API/worker images, runs import/CLI smoke checks, applies Alembic migrations, recreates services, verifies the running revision locally, and verifies the same revision through the Caddy/TLS route.

Release `0.2.0` introduced migration `0006_user_password_hash`, following `0005_edge_control_plane`. Release `0.2.1` adds no database migration; the normal release script remains the supported deployment path.

## Current hardening boundary

Before broad multi-site customer deployment:

- enforce paired Edge credential → assigned-site affinity for `edge:ingest`
- add request throttling to unauthenticated pairing-start
- validate live WebSocket delivery from an Edge-created event
- complete backup/restore and reboot/startup validation
- load-test and tune the configured node/member limits against Oracle resources
- add retention/audit/rate-limit policy appropriate to partner operational data

## Radio safety

TerraSatch must not infer transmit capability from receive hardware. Nooelec / RTL-SDR is receive-only. TX state in the API represents provider-reported capability plus explicit operator policy; actual RF transmission requires a dedicated TX-capable provider/adapter and remains gated separately from the API control plane.

Operators are responsible for receiving and processing only traffic they are authorized to access. Secrets belong in environment variables or ignored owner-only files and must never be committed.
