# TerraSatch AI Radio Core Checklist

Status values: `completed`, `in progress`, `blocked by physical hardware`, `not started`.

This checklist reflects code that exists in the repository. A phase is not marked `completed`
merely because a model, placeholder, deployment example, or future-facing interface exists.

| Phase | Status | Current implementation / remaining work |
| --- | --- | --- |
| 0. Repository isolation | completed | Independent Git repository, ignore rules, README, and project checklist. TerraSatch demos/frontends remain separate API clients. |
| 1. Backend foundation | completed | Python 3.12, FastAPI, Typer, Pydantic settings, structured logging, PostgreSQL, Redis, Docker/Compose, Alembic, worker heartbeat, health checks, request IDs, and tests. |
| 2. Multi-tenant core | in progress | Account, Organization, Site, Team, User, Membership, tenant-derived bearer authorization, hashed API keys, scopes, site lifecycle API, Team lifecycle API, and API-key management exist. Human User/Membership services/authentication and complete CLI coverage remain. |
| 3. External application platform | in progress | Explicit CORS, browser admin sessions, tenant-scoped service API keys, protected REST operations, and authenticated tenant-scoped WebSockets exist. ClientApplication registration, per-application origins, browser/demo token exchange, and application-specific credentials remain. |
| 4. Plugin interfaces | in progress | `IntelligenceProvider` protocol exists and TerraEngine is provider-neutral. InputSource, RadioReceiver, SpeechToTextProvider, StorageProvider, BillingProvider, and a general plugin registry remain. |
| 5. Agent and radio models | in progress | Agent, Channel, Callsign, Transmission, Transcript, and OperationalEvent models/services/APIs exist with lifecycle control for configuration resources. Dedicated Source, Keyword, Rule, and richer configurable radio-profile models remain. |
| 6. Simulator | in progress | `terrasatch simulate radio` is implemented and feeds the same ingest → transcript → TerraEngine → event → PostgreSQL → Redis path used by the REST ingest endpoint. Oracle acceptance validation remains before calling the phase complete. |
| 7. Real audio | not started | WAV, microphone/audio-device sources, buffering, VAD, segmentation, and local/cloud STT abstractions remain. |
| 8. RTL-SDR / Nooelec | not started | Device discovery, `rtl_test`/`rtl_fm` adapter, radio-profile tuning, demodulation, and signal diagnostics remain. |
| 9. Edge agent | not started | EdgeDevice/DeviceCredential, outbound authenticated connection, reconnect, durable queue, heartbeat, and store-and-forward remain. A systemd deployment example is not an implementation of the edge process. |
| 10. TerraEngine | in progress | Provider-neutral TerraEngine, validated Pydantic event output, deterministic offline extraction, provenance, confidence, event classification, callsign/aspect/elevation extraction, and source-linked persistence exist. Model-backed providers, richer context/rules, and industry-specific extraction profiles remain. |
| 11. Operations intelligence | not started | Incidents, incident threading, shifts, summaries, task/rule actions, and operational context remain. |
| 12. Official realtime API | in progress | Versioned REST, OpenAPI, auth, sites/teams/API keys, agents/channels/callsigns, transmissions, transcripts, events, filters, detail routes, Redis event publication, and authenticated WebSocket subscriptions exist. Durable outbox delivery and production webhooks remain. |
| 13. TypeScript SDK | not started | `@terrasatch/client` typed REST/WebSocket client, reconnection, errors, and generated types remain. |
| 14. Usage and billing | not started | Plans, subscriptions, entitlements, usage records, pilots, plan-aware limits, BillingProvider, and optional Stripe adapter remain. |
| 15. Security, retention, audit | in progress | API-key hashing, password hashing, tenant authorization, request validation, secret isolation, explicit CORS, secure admin sessions, and TLS deployment exist. Retention jobs, durable audit records, rate limiting, storage cleanup, webhook verification, and full security review remain. |
| 16. Deployment | in progress | Docker, Compose, Caddy, production configuration examples, and the Oracle deployment at `api.terrasatch.com` exist. Remaining hardening includes reboot/startup verification, backup/restore validation, reserved-IP planning, and repeatable release verification. |
| 17. Live demo | blocked by physical hardware | The software simulator path is implemented pending Oracle acceptance. Physical BCA → Nooelec → Linux/Edge → API → TerraEngine → Event → WebSocket acceptance remains blocked until hardware/audio phases are implemented. |

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
- [x] Branded public API landing/status page exists.
- [x] Admin environment writer safely quotes Compose-sensitive `$` password hashes.
- [x] Migration `0004_radio_event_pipeline` is present for the radio/event domain.
- [x] REST contracts for agents, channels, callsigns, transmissions, transcripts, and events exist.
- [x] Redis-backed tenant-scoped WebSocket event subscriptions exist.
- [ ] Run the new simulator acceptance workflow on Oracle and verify the same events through REST.
- [ ] Verify a live WebSocket subscriber receives simulator-created events on Oracle.
- [ ] Reboot/startup persistence validated end-to-end on the production VM.
- [ ] Reserved/static Oracle public IP configured.
- [ ] Automated PostgreSQL backup/restore procedure validated.

## Software acceptance workflow

The software path is designed to work without physical radio hardware:

```text
Simulator / REST ingest
  → Transmission
  → Transcript
  → TerraEngine
  → OperationalEvent
  → PostgreSQL
  → Redis event bus
  → REST API
  → WebSocket
```

Acceptance commands:

```bash
terrasatch org create "TerraSatch Demo"
terrasatch site create "Wasatch Demo" --organization "TerraSatch Demo"
terrasatch callsign add --name "Patrol 4" --organization "TerraSatch Demo"
terrasatch agent create --name "demo-agent" --profile ski_patrol \
  --organization "TerraSatch Demo" --site "Wasatch Demo"
terrasatch simulate radio --organization "TerraSatch Demo" --site "Wasatch Demo"
terrasatch event list --organization "TerraSatch Demo"
```

The same persisted events must be available to an authorized client through:

```text
GET /api/v1/events
GET /api/v1/events/{event_id}
WS  /ws/v1/events
```

Do not create a separate fake demo intelligence path. Simulator, recorded audio, live audio,
RTL-SDR, and the future Edge Agent must converge on the same production processing pipeline.

## Next engineering sequence after software acceptance

1. Connect one existing partner/demo frontend to the authenticated REST + WebSocket contract.
2. Add WAV/file audio input and a `SpeechToTextProvider` interface.
3. Add local microphone/audio-device capture and segmentation/VAD.
4. Add RTL-SDR/Nooelec receive adapters.
5. Add the outbound Edge Agent and durable store-and-forward queue.
6. Add durable outbox/webhooks, SDK, rate limits, retention/audit, then billing/entitlements.
