# TerraSatch AI Radio Core Checklist

Status values: `completed`, `in progress`, `blocked by physical hardware`, `not started`.

| Phase | Status | Deliverable |
| --- | --- | --- |
| 0. Repository isolation | completed | Independent repository, ignore rules, README, and this checklist |
| 1. Backend foundation | completed | Python project, FastAPI, CLI, configuration, logging, PostgreSQL, Redis, Docker, Alembic, worker heartbeat, health checks |
| 2. Multi-tenant core | in progress | Account, Organization, Site, Team/User/Membership models, tenant-derived authorization, hashed API keys, scopes, organization/site and API-key control plane. Full Team/User/Membership management remains. |
| 3. External application platform | in progress | Explicit CORS, browser admin session, and server API keys exist. ClientApplication registration and browser/demo token architecture remain. |
| 4. Plugin interfaces | not started | Registered, trusted input/provider/storage/billing interfaces remain; TerraEngine now has an initial IntelligenceProvider protocol on the pipeline branch. |
| 5. Agent and radio models | in progress | Agent, Channel, Callsign, Transmission, Transcript, and OperationalEvent models/services are implemented on `agent/core-radio-event-pipeline`. Sources, keywords, rules, and radio profiles remain. |
| 6. Simulator | in progress | `terrasatch simulate radio` now feeds the same ingestion → transcript → TerraEngine → event persistence service used by API ingestion. Full integration validation remains. |
| 7. Real audio | not started | WAV and audio-device sources, VAD, segmentation, STT |
| 8. RTL-SDR / Nooelec | not started | Discovery, `rtl_fm` adapter, signal diagnostics |
| 9. Edge agent | not started | Scoped credentials, durable queue, reconnect, heartbeat |
| 10. TerraEngine | in progress | Provider-neutral TerraEngine plus deterministic structured extraction exists on the pipeline branch. Context, industry profiles, and model-backed providers remain. |
| 11. Operations intelligence | not started | Incidents, shifts, rules, summaries |
| 12. Official realtime API | in progress | Existing REST foundation plus pipeline-branch agents/channels/callsigns/transmissions/transcripts/events REST resources, Redis event publication, and `/ws/v1/events`. Durable outbox and webhooks remain. |
| 13. TypeScript SDK | not started | `@terrasatch/client` REST and WebSocket package |
| 14. Usage and billing | not started | Entitlements, metering, pilots, billing provider |
| 15. Security, retention, audit | in progress | Hashed service credentials, tenant authorization, scopes, validation, CORS, and TLS assumptions exist. Retention jobs, rate limiting, audit logs, and security review remain. |
| 16. Deployment | in progress | Docker, Compose, systemd, Caddy HTTPS/WSS, and public Oracle deployment guidance exist. Production hardening/backup/reboot validation remain. |
| 17. Live demo | blocked by physical hardware | Software pipeline is being implemented; physical RTL-SDR/BCA acceptance remains blocked until hardware integration is complete. |

## Current validation

- [x] Independent repository initialized and sibling TerraSatch frontends remain separate.
- [x] Python 3.12 project foundation.
- [x] FastAPI startup and health endpoint validation.
- [x] PostgreSQL and Redis readiness architecture.
- [x] Tenant-scoped API key authorization foundation.
- [x] Agent/Channel/Callsign/Transmission/Transcript/OperationalEvent migration added on pipeline branch.
- [x] Deterministic TerraEngine provider and validated Pydantic output contract added on pipeline branch.
- [x] REST contract added for agents, channels, callsigns, transmissions, transcripts, and events.
- [x] Tenant-scoped Redis normalized event publication added.
- [x] `/ws/v1/events` subscription path added with first-message API token authentication and topic scopes.
- [x] CLI groups added for agents, channels, callsigns, events, and `simulate radio`.
- [ ] Pipeline branch lint and full test suite run in a checked-out development environment.
- [ ] Alembic `0004_radio_event_pipeline` migration exercised against PostgreSQL.
- [ ] End-to-end simulator → database → REST → WebSocket acceptance test completed.
- [ ] Real audio/STT path implemented.
- [ ] RTL-SDR/Nooelec path implemented and physically validated.

## Software acceptance target

Without physical hardware, the following must work after the pipeline branch is validated and merged:

```text
Simulator
  → Transmission
  → Transcript
  → TerraEngine
  → OperationalEvent
  → PostgreSQL
  → Redis event bus
  → REST API
  → WebSocket
```

Expected operator workflow:

```bash
terrasatch org create "TerraSatch Demo"
terrasatch site create "Wasatch Demo" --organization "TerraSatch Demo"
terrasatch callsign add --name "Patrol 4" --organization "TerraSatch Demo"
terrasatch agent create --name "demo-agent" --profile ski_patrol \
  --organization "TerraSatch Demo" --site "Wasatch Demo"
terrasatch simulate radio --organization "TerraSatch Demo" --site "Wasatch Demo"
terrasatch event list --organization "TerraSatch Demo"
```

An authorized external client must then be able to retrieve the same persisted events through:

```text
GET /api/v1/events
```

and subscribe to new normalized events through:

```text
wss://api.terrasatch.com/ws/v1/events
```

The simulator is an input fixture only. It must never insert fabricated event rows directly; all
simulation messages pass through the same ingestion and TerraEngine service used by external input.
