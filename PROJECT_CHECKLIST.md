# TerraSatch API Checklist

Status values: `completed`, `in progress`, `not started`.

This checklist tracks the API/backend repository. Field-side hardware discovery and runtime behavior live in the separate `terrasatch-edge` repository and are called out here only where they affect the production API contract.

| Phase | Status | Current implementation / remaining work |
| --- | --- | --- |
| 0. Repository isolation | completed | API/backend remains isolated from TerraSatch demos, partner frontends, and the dedicated Edge client. |
| 1. Backend foundation | completed | Python 3.12, FastAPI, structured logging, PostgreSQL, Redis, Docker/Compose, Alembic, worker heartbeat, health checks, request IDs, and release smoke checks. |
| 2. Multi-tenant core | in progress | Accounts, organizations, sites, teams, users, memberships, tenant-derived bearer auth, hashed API keys, scopes, browser administration, and organization member portal are live. |
| 3. External application platform | in progress | CORS, service credentials, browser sessions, tenant-scoped REST, authenticated WebSockets, superadmin, and organization portal exist. Application-specific credentials/origins and browser token exchange remain. |
| 4. Plugin interfaces | in progress | `IntelligenceProvider` protocol, provider-neutral TerraEngine, and generalized Garmin/mobile field-input adapters exist. Speech-to-text, generalized binary-media storage, billing, and plugin registry work remain. |
| 5. Agent and radio models | in progress | Agent, Channel, Callsign, Transmission, Transcript, OperationalEvent, EdgeDevice, EdgePairing, remote radio policy, and Satchy AI-channel configuration exist. Richer rules/source/profile models remain. |
| 6. Simulator | completed | Simulator feeds the same canonical ingest → transcript → TerraEngine → event → PostgreSQL → Redis path as REST/Edge ingestion. |
| 7. Real audio / STT | not started | WAV/microphone ingestion, buffering, VAD, segmentation, and SpeechToTextProvider implementations remain. |
| 8. RTL-SDR / Nooelec | in progress | API capability model and Edge inventory reporting are live. The dedicated Edge client has physically detected a NESDR SMArt v5 in Linux/WSL and completed a bounded RTL-SDR IQ receive probe. RF demodulation → audio → STT is the next field-side phase. |
| 9. Edge control plane | completed | Browser pairing, device credential issuance, Edge registry, `/edge/me`, heartbeat, hardware inventory, remote config, live fleet health, and configurable registration limits are implemented. Durable offline queue/store-and-forward remains a field-client enhancement. |
| 10. TerraEngine | in progress | Deterministic provider-neutral extraction, provenance, confidence, event classification, callsign/aspect/elevation extraction, and source-linked persistence are live. Model-backed providers and industry-specific extraction profiles remain. |
| 11. Operations intelligence | in progress | Append-only Discovery evidence, immutable revisions, evidence-derived workflow state/counts, automatic canonical signal capture, and new-run workspace-context capture are implemented. Bounded workflow pattern detection, incident threading, shifts, summaries, and richer operational context remain. |
| 12. Realtime API | in progress | Versioned REST, OpenAPI, Redis publication, filters, detail routes, authenticated tenant WebSockets, Edge control plane, fleet health, and public aggregate network status are implemented. Durable outbox/webhooks remain. |
| 13. TypeScript SDK | in progress | Dependency-free REST/WebSocket client, OpenAPI-backed declarations, workspace/convergence response contracts, and SDK drift gates are production. Satchy consumer migration is staged; broader demo adoption remains. |
| 14. Usage and billing | not started | Plans, entitlements, usage, billing adapters, and subscription enforcement remain. |
| 15. Security, retention, audit | in progress | API-key hashing, scrypt browser passwords, CSRF, tenant authorization, explicit CORS, secure sessions, TLS, provider-gated TX policy, and onboarding capacity guardrails exist. Request-rate limiting, durable audit, retention, cleanup, and full security review remain. |
| 16. Deployment | in progress | Oracle deployment, Docker/Compose, Caddy/TLS, release script, revision verification, and public readiness checks exist. Backup/restore, reboot persistence, reserved-IP hardening, and load-tested capacity tuning remain. |
| 17. Live field path | in progress | Production Edge pairing, heartbeat, hardware sync, text ingestion, transcript creation, and structured TerraEngine event extraction have been validated. Garmin inReach IPC Outbound and authenticated mobile observation adapters now target the same canonical ingest path; live Garmin acceptance, mobile media upload/offline sync, and physical RF → demodulated audio → STT remain. |

## Production validation

- [x] Public `api.terrasatch.com` health/readiness path.
- [x] PostgreSQL and Redis readiness.
- [x] Tenant-scoped bearer authorization and API-key hashing.
- [x] Browser superadmin console with CSRF-protected sessions.
- [x] Edge pairing and credential issuance against the public HTTPS API.
- [x] Edge heartbeat and hardware inventory synchronization.
- [x] Registered fleet health and provider-aware RX/TX capability model.
- [x] Linux Edge node paired to production.
- [x] NESDR SMArt v5 / RTL2838 detected in Linux/WSL and IQ receive probe completed.
- [x] Edge text transmission accepted by production.
- [x] Transcript persisted through the canonical production path.
- [x] TerraEngine extracted a WEATHER event with callsign, east aspect, and 9,800 ft elevation from an Edge submission.
- [x] Migration `0005_edge_control_plane` exists.
- [x] Migration `0006_user_password_hash` deployed with API `0.2.0`.
- [ ] Deploy migration `0026_workspace_discovery_events` after isolated QA.
- [x] Production API `0.2.0` verified at revision `94da98f56b3f` through Caddy/TLS.
- [ ] Deploy and smoke-test API `0.2.1` public network totals and registration guardrails.
- [ ] Validate organization portal/member workflows after `0.2.1` deployment.
- [ ] Validate a live WebSocket subscriber receives an Edge-created event.
- [ ] Enforce paired Edge credential → assigned-site binding before broad multi-site customer deployment.
- [ ] Add request throttling to unauthenticated pairing-start before high-volume public exposure.
- [ ] Load-test Oracle and tune `TERRASATCH_MAX_EDGE_DEVICES` / `TERRASATCH_MAX_PORTAL_USERS` from measured capacity.
- [ ] Validate production VM reboot/startup persistence.
- [ ] Validate PostgreSQL backup/restore procedure.

## Canonical processing path

```text
Simulator / reviewed Edge text / Garmin inReach / TerraSatch Mobile / future STT
  → Transmission
  → Transcript
  → TerraEngine
  → OperationalEvent
  → PostgreSQL
  → Redis event bus
  → REST + WebSocket clients
```

Do not create a separate demo-only intelligence path. Simulator, recorded audio, live audio, RTL-SDR, and Edge must converge on this production pipeline.

## Next engineering sequence

1. Validate automatic Discovery signal/context capture through isolated Oracle QA and production smoke checks.
2. Build bounded workflow-pattern detection that can propose `workflow_identified` evidence without auto-approving it.
3. Add measured workflow-testing evidence and human approval/rejection transitions for Discovery recommendations.
4. Keep the dedicated Edge client running continuous heartbeats and hardware inventory.
5. Add bounded RTL-SDR demodulated audio capture, VAD/STT, and submit recognized speech into the existing transmission endpoint.
6. Continue Edge → site affinity, pairing throttling, durable offline queue/store-and-forward, outbox/webhooks, audit/retention, and billing.
