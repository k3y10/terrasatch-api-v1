# TerraSatch AI Radio Core Checklist

Status values: `completed`, `in progress`, `blocked by physical hardware`, `not started`.

This checklist reflects code that exists in the repository today. A phase is not marked
`completed` merely because a model, placeholder, deployment example, or future-facing interface
exists.

| Phase | Status | Current implementation / remaining work |
| --- | --- | --- |
| 0. Repository isolation | completed | Independent Git repository, ignore rules, README, and project checklist. Existing TerraSatch demos/frontends remain separate clients. |
| 1. Backend foundation | completed | Python 3.12 project, FastAPI, Typer CLI, Pydantic settings, structured logging, PostgreSQL, Redis, Docker/Compose, Alembic, worker heartbeat, health checks, request IDs, and tests. |
| 2. Multi-tenant core | in progress | Account, Organization, Site, Team, User, Membership, tenant-derived bearer authorization, hashed API keys, scope enforcement, organization/site services, and API-key management exist. Full Team/User/Membership services, APIs, and CLI coverage remain. |
| 3. External application platform | in progress | Explicit configured CORS, browser admin sessions, server API keys, and tenant-safe protected REST operations exist. ClientApplication registration, per-application origins, browser/demo token architecture, and WebSocket authorization remain. |
| 4. Plugin interfaces | not started | Stable InputSource, RadioReceiver, SpeechToTextProvider, IntelligenceProvider, StorageProvider, BillingProvider, and plugin registry remain to be implemented. |
| 5. Agent and radio models | not started | Agent, channel, callsign, source, keyword, rule, and configurable radio-profile models/services remain. |
| 6. Simulator | not started | Must feed the same ingestion → transcript → TerraEngine → event → persistence → realtime pipeline that physical sources will use. |
| 7. Real audio | not started | WAV, microphone/audio-device sources, buffering, VAD, segmentation, and local/cloud STT abstractions remain. |
| 8. RTL-SDR / Nooelec | not started | Device discovery, `rtl_test`/`rtl_fm` adapter, radio profile tuning, demodulation, and signal diagnostics remain. |
| 9. Edge agent | not started | EdgeDevice/DeviceCredential, outbound authenticated connection, reconnect, durable queue, heartbeat, and store-and-forward remain. A systemd example exists but is not an implementation of the edge process. |
| 10. TerraEngine | not started | Validated structured extraction, deterministic development provider, pluggable intelligence provider, context, provenance, confidence, and industry profiles remain. |
| 11. Operations intelligence | not started | Incidents, incident threading, shifts, summaries, task/rule actions, and operational context remain. |
| 12. Official realtime API | in progress | Versioned REST foundation, OpenAPI, authentication, sites/API-key control plane, and public reference endpoints exist. Transmission/transcript/event resources, Redis event bus, WebSocket subscriptions, and webhooks remain. |
| 13. TypeScript SDK | not started | `@terrasatch/client` typed REST/WebSocket client, reconnection, errors, and generated types remain. |
| 14. Usage and billing | not started | Plans, subscriptions, entitlements, usage records, pilots, rate limits, BillingProvider, and optional Stripe adapter remain. |
| 15. Security, retention, audit | in progress | API-key hashing, password hashing, tenant authorization, request validation, secret isolation, explicit CORS, and TLS deployment exist. Retention jobs, audit records, plan-aware rate limiting, storage cleanup, webhook verification, and full security review remain. |
| 16. Deployment | in progress | Docker, Compose, systemd examples, Caddy config, production configuration examples, and public Oracle deployment at `api.terrasatch.com` exist. Remaining hardening includes restart persistence, backup/restore validation, reserved-IP planning, and repeatable deployment verification. |
| 17. Live demo | blocked by physical hardware | Software simulator pipeline is not built yet. Physical BCA → Nooelec → Linux → TerraSatch Edge → API → TerraEngine → Event → WebSocket acceptance remains blocked until both the software path and hardware integration exist. |

## Current production validation

- [x] Repository remains isolated from TerraSatch frontend/demo repositories.
- [x] FastAPI startup and health endpoint validation.
- [x] PostgreSQL readiness validation.
- [x] Redis readiness validation.
- [x] Worker heartbeat foundation.
- [x] Tenant-scoped hashed API keys and bearer authorization.
- [x] Organization and site administration.
- [x] Browser admin console foundation.
- [x] Public DNS for `api.terrasatch.com` points to the Oracle deployment.
- [x] Caddy terminates public HTTP/HTTPS for the API host.
- [x] Public API is served behind Caddy while raw port 8000 remains loopback-only.
- [x] Root API host has a lightweight branded status/entry page on the `agent/api-platform-and-landing` update branch.
- [x] Admin environment writer on the update branch safely quotes Compose-sensitive `$` password hashes.
- [ ] Reboot/startup persistence validated end-to-end on the production VM.
- [ ] Reserved/static Oracle public IP configured.
- [ ] Automated PostgreSQL backup/restore procedure validated.

## Next software acceptance milestone

The next product milestone must work without physical radio hardware:

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

Minimum acceptance behavior:

```bash
terrasatch org create "TerraSatch Demo"
terrasatch site create "Wasatch Demo" --organization "TerraSatch Demo"
terrasatch callsign add --name "Patrol 4" --organization "TerraSatch Demo"
terrasatch agent create --name "demo-agent" --profile ski_patrol \
  --organization "TerraSatch Demo" --site "Wasatch Demo"
terrasatch simulate radio --organization "TerraSatch Demo" --site "Wasatch Demo"
terrasatch event list --organization "TerraSatch Demo"
```

The same persisted events must then be available to an authorized client through:

```text
GET /api/v1/events
WS  /ws/v1/events
```

Do not create a separate fake demo intelligence path. The simulator, recorded audio, real audio,
RTL-SDR, and Edge Agent must converge on the same production processing pipeline.
