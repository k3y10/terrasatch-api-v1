# TerraSatch AI Radio Core Checklist

Status values: `completed`, `in progress`, `blocked by physical hardware`, `not started`.

| Phase | Status | Deliverable |
| --- | --- | --- |
| 0. Repository isolation | completed | Independent repository, ignore rules, README, and this checklist |
| 1. Backend foundation | completed | Python project, FastAPI, CLI, configuration, logging, PostgreSQL, Redis, Docker, Alembic, worker heartbeat, health checks |
| 2. Multi-tenant core | not started | Tenant models, server-side authorization, API key hashing |
| 3. External application platform | not started | Client apps, explicit CORS, browser and WebSocket authorization |
| 4. Plugin interfaces | not started | Registered, trusted input/provider/storage/billing interfaces |
| 5. Agent and radio models | not started | Agent, channel, callsign, rule, and configurable radio profile models |
| 6. Simulator | not started | Same ingestion-to-event pipeline used by all sources |
| 7. Real audio | not started | WAV and audio-device sources, VAD, segmentation, STT |
| 8. RTL-SDR / Nooelec | not started | Discovery, `rtl_fm` adapter, signal diagnostics |
| 9. Edge agent | not started | Scoped credentials, durable queue, reconnect, heartbeat |
| 10. TerraEngine | not started | Validated structured extraction, context, and industry profiles |
| 11. Operations intelligence | not started | Incidents, shifts, rules, summaries |
| 12. Official realtime API | not started | REST resources, event bus, WebSockets, webhooks |
| 13. TypeScript SDK | not started | `@terrasatch/client` REST and WebSocket package |
| 14. Usage and billing | not started | Entitlements, metering, pilots, billing provider |
| 15. Security, retention, audit | not started | Retention jobs, rate limiting, audit logs, security review |
| 16. Deployment | in progress | Docker, Compose, systemd, Caddy HTTPS/WSS, public deployment verification guidance |
| 17. Live demo | blocked by physical hardware | Physical RTL-SDR/BCA acceptance workflow |

## Current validation

- [x] Target repository is `/home/k3y10/terrasatch-ai-radio-core`.
- [x] Independent Git repository initialized.
- [x] Existing TerraSatch repositories left unmodified.
- [x] Python 3.12 project install and lint validation.
- [x] FastAPI startup and health endpoint validation.
- [x] Docker PostgreSQL and Redis readiness validation.
- [ ] Public DNS, TLS, and `https://api.terrasatch.com/health/ready` validation.