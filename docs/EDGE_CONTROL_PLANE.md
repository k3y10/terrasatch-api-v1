# TerraSatch Edge Control Plane

This document describes the first server-side control plane used by `terrasatch-edge`.

## Pairing workflow

1. Edge calls `POST /api/v1/edge/pairings` without a credential.
2. The API returns a high-entropy `device_code`, short `user_code`, verification URL, expiry, and polling interval.
3. The operator opens the verification URL, signs into the existing TerraSatch admin console, selects an organization/site, and approves the short code.
4. Edge polls `POST /api/v1/edge/pairings/token` with the high-entropy device code.
5. Once approved, the API creates a registered `edge_device` and mints a tenant-scoped service key.
6. The raw service key is returned once to Edge and only its SHA-256 digest remains in the API credential store.
7. Edge uses that credential for `/api/v1/edge/me`, `/api/v1/edge/heartbeat`, `/api/v1/edge/config`, and the existing `edge:ingest` transmission path.

Pairings expire after 10 minutes.

## Management scopes

- `edge:connect` — device self identity, heartbeat, and configuration retrieval
- `edge:ingest` — existing transmission ingestion
- `read:edge` — list tenant Edge devices
- `write:edge` — approve pairings and update device configuration/status
- `admin` — remains the tenant-local wildcard

Device credentials minted by pairing currently receive `edge:connect`, `edge:ingest`, and `read:sites`.

## Persistent resources

`edge_pairings` stores only a hash of the high-entropy device code. It also stores the human code, request metadata, expiry, approval state, tenant/site binding, and claim state.

`edge_devices` links a registered field node to its tenant, site, service credential, machine identity, agent version, hardware inventory, capability set, remote configuration, enabled state, and last heartbeat time.

## Deployment

This branch adds Alembic revision `0005_edge_control_plane`.

Before restarting the production API after merge:

```bash
uv run alembic upgrade head
```

Then restart the API using the existing Oracle release process and verify:

```text
GET /health/ready
GET /api/v1/reference
```

The reference payload should include the Edge routes and the `edge:connect`, `read:edge`, and `write:edge` scopes.

## Current hardening boundary

The paired device credential is tenant-scoped. The current `POST /api/v1/transmissions` implementation validates `edge:ingest` plus organization ownership, but does not yet force an Edge credential to ingest only into the `site_id` assigned to its `edge_device`.

Before multi-site customer deployment, add device/site binding enforcement to the ingestion endpoint.

Also add edge-level request throttling for the unauthenticated pairing-start endpoint before exposing it to high-volume public traffic.
