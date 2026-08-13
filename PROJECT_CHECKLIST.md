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
| 4. Plugin interfaces | in progress | `IntelligenceProvider` protocol exists and TerraEngine is provider-neutral. A receive-side RTL helper and outbound edge submission client now exist, but generalized InputSource, RadioReceiver, SpeechToTextProvider, StorageProvider, BillingProvider, and a plugin registry remain. |
| 5. Agent and radio models | in progress | Agent, Channel, Callsign, Transmission, Transcript, and OperationalEvent models/services/APIs exist with lifecycle control for configuration resources. Dedicated Source, Keyword, Rule, and richer configurable radio-profile models remain. |
| 6. Simulator | in progress | `terrasatch simulate radio` is implemented and feeds the same ingest → transcript → TerraEngine → event → PostgreSQL → Redis path used by the REST ingest endpoint. Production acceptance validation remains before calling the phase complete. |
| 7. Real audio | in progress | Receive-side WAV capture/inspection is implemented for RTL-SDR output. Microphone/line-in sources, VAD, segmentation, speech-to-text adapters, confidence, and automatic transcript creation remain. |
| 8. RTL-SDR / Nooelec | in progress | Edge commands discover `rtl_test`/`rtl_fm`, run a bounded device probe, build receive-only tuning commands, and capture signed-16-bit mono WAV files from an RTL-SDR/Nooelec receiver. Physical-device validation, radio profiles, squelch/VAD segmentation, and long-running supervised receive remain. |
| 9. Edge agent | not started | The edge CLI can diagnose hardware, capture bounded receive audio, and submit authorized manual transcripts outbound to the API. EdgeDevice/DeviceCredential, reconnect, durable queue, heartbeat, automatic STT forwarding, and store-and-forward remain. The systemd unit is intentionally only a one-shot readiness check. |
| 10. TerraEngine | in progress | Provider-neutral TerraEngine, validated Pydantic event output, deterministic offline extraction, provenance, confidence, event classification, callsign/aspect/elevation extraction, and source-linked persistence exist. Model-backed providers, richer context/rules, and industry-specific extraction profiles remain. |
| 11. Operations intelligence | not started | Incidents, incident threading, shifts, summaries, task/rule actions, and operational context remain. |
| 12. Official realtime API | in progress | Versioned REST, OpenAPI, auth, sites/teams/API keys, agents/channels/callsigns, transmissions, transcripts, events, filters, detail routes, Redis event publication, and authenticated WebSocket subscriptions exist. Durable outbox delivery and production webhooks remain. |
| 13. TypeScript SDK | not started | `@terrasatch/client` typed REST/WebSocket client, reconnection, errors, and generated types remain. |
| 14. Usage and billing | not started | Plans, subscriptions, entitlements, usage records, pilots, plan-aware limits, BillingProvider, and optional Stripe adapter remain. |
| 15. Security, retention, audit | in progress | API-key hashing, password hashing, tenant authorization, request validation, secret isolation, explicit CORS, secure admin sessions, and TLS deployment exist. Retention jobs, durable audit records, rate limiting, storage cleanup, webhook verification, and full security review remain. |
| 16. Deployment | in progress | Docker, Compose, Caddy, production configuration examples, runtime revision reporting, restart policies, and repeatable Oracle release verification exist. Remaining hardening includes reboot/startup verification, backup/restore validation, and reserved-IP planning. |
| 17. Live demo | blocked by physical hardware | The software simulator path and a receive-side hardware acceptance workflow exist. Physical BCA → Nooelec → WAV validation remains to be run on the user's edge workstation. Automatic RF → STT → API acceptance remains blocked until VAD/STT is implemented. |

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
- [x] Branded public API radio console exists.
- [x] Health responses identify the running build revision.
- [x] Admin environment writer safely quotes Compose-sensitive `$` password hashes.
- [x] Migration `0004_radio_event_pipeline` is present for the radio/event domain.
- [x] REST contracts for agents, channels, callsigns, transmissions, transcripts, and events exist.
- [x] Redis-backed tenant-scoped WebSocket event subscriptions exist.
- [x] Oracle release script performs read-only syntax/import/CLI checks, Alembic, recreation, and Caddy health verification.
- [ ] Run the simulator acceptance workflow on Oracle and verify the same events through REST.
- [ ] Verify a live WebSocket subscriber receives simulator-created events on Oracle.
- [ ] Run `terrasatch edge doctor --check-api` on the Nooelec edge workstation.
- [ ] Validate `terrasatch edge devices` against the physical receiver.
- [ ] Capture an authorized BCA test transmission to WAV with `terrasatch edge capture-rtl`.
- [ ] Confirm the captured WAV is intelligible and submit the spoken phrase through `terrasatch edge acceptance`.
- [ ] Add VAD/STT and prove automatic RF → transcript → TerraEngine acceptance.
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

## Receive-side hardware acceptance workflow

The first physical milestone deliberately separates RF/audio validation from automatic STT:

```text
BCA radio (manual operator TX)
  → Nooelec / RTL-SDR receive
  → rtl_fm demodulation
  → WAV capture
  → operator confirms intelligible audio
  → manual transcript submitted with edge:ingest credential
  → Transmission / Transcript / TerraEngine / OperationalEvent
  → PostgreSQL / Redis / REST / WebSocket
```

Commands on the edge workstation:

```bash
terrasatch edge doctor --check-api
terrasatch edge devices
terrasatch edge capture-rtl --frequency-hz <AUTHORIZED_HZ> --seconds 10 --output terrasatch-bca-test.wav
terrasatch edge inspect-wav terrasatch-bca-test.wav
terrasatch edge acceptance --frequency-hz <AUTHORIZED_HZ> --site <SITE_UUID> \
  --text "Patrol 4 to base. Wind loading observed on the east aspect around 9800 feet." \
  --callsign "Patrol 4" --seconds 10 --output terrasatch-bca-test.wav --json
```

The acceptance command must continue to report `automatic_stt_validated: false` until a real
speech-to-text provider has generated the transcript from captured audio.

## Next engineering sequence

1. Validate the software simulator and WebSocket path on Oracle.
2. Validate the bounded BCA → Nooelec → WAV → manual transcript hardware acceptance flow.
3. Add WAV/file + microphone sources behind a generalized input interface.
4. Add VAD/squelch-aware segmentation and a `SpeechToTextProvider` abstraction.
5. Add a local STT provider and feed recognized text into the existing transmission service automatically.
6. Add the outbound Edge Agent with reconnect, durable queue, heartbeat, and store-and-forward.
7. Add durable outbox/webhooks, SDK, rate limits, retention/audit, then billing/entitlements.
