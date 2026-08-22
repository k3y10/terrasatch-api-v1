# TerraSatch Control Plane and Master Data — Phase 1

This phase adds a canonical source/provenance foundation around the working radio pipeline. It does
not replace or reroute Edge ingestion, TerraEngine, PostgreSQL event persistence, Redis realtime, or
the partner event API.

## Repository audit

| Area | Existing implementation | Phase 1 decision |
| --- | --- | --- |
| Tenancy | `Account`, `Organization`, `Site`, `Team`, membership roles | Reuse without duplication |
| Credentials | Tenant-derived API keys, hashed secrets, scopes | Reuse; source connections store only credential references |
| Live radio | `Transmission → Transcript → OperationalEvent` in one transaction | Preserve unchanged |
| Intelligence | Deterministic TerraEngine with optional providers and fallback | Preserve unchanged |
| Edge fleet | Pairing, device identity, heartbeat, inventory, capability gates | Reuse; heartbeat history remains future work |
| Realtime | Tenant-scoped Redis publication and worker heartbeat | Preserve unchanged |
| Workers | Separate supervised worker process | Reuse later for source-sync consumers; API requests only queue work |
| Admin security | Session authentication, CSRF validation, allow-listed commands | Extend with data pages and commands |
| Diagnostics | Database/Redis readiness, worker heartbeat, quality catalog | Reuse and extend through safe commands |
| Migrations | Linear Alembic revisions through `0006` | Add one expand-only `0007` revision |
| Deployment | Consolidated FastAPI/worker/Redis plus PostgreSQL | Preserve pilot topology; no microservice split |

## Additive schema

Revision `0007_control_plane_master_data` adds:

- `data_sources`: tenant-scoped provider and adapter configuration, disabled by default.
- `source_connections`: endpoint, Vault/secret-manager reference, cursor, ETag, and sync state.
- `source_sync_runs`: queued/running/completed job state and bounded counters.
- `source_records`: authoritative provider identity, checksum, versioning, and Object Storage pointer.
- `regions`: pilot forecast/provider/operational geometry.
- `terrain_cells`: stable TerraSatch IDs such as `TS-UT-SLC-004813`.
- `terrain_cell_sources`: lineage between stable cells and the records that defined them.
- `observations`: normalized provider facts that may link to the existing `OperationalEvent` model.
- `data_quality_flags`: unresolved location, geometry, schema, timestamp, and normalization issues.
- `audit_log`: append-only browser-admin and operations-command history.
- `backup_snapshots`: backup state, retention, and restore-test evidence.

The revision also adds nullable `region_id`, `terrain_cell_id`, and `spatial_status` fields to
`operational_events`. Existing rows and the existing Edge payload remain valid. No existing field is
renamed, removed, or made more restrictive.

`Observation` is not a second event architecture. It stores a normalized source fact. Actionable
operational intelligence continues to use the existing `OperationalEvent` record.

## PostGIS policy

The migration enables PostGIS on PostgreSQL, creates SRID 4326 region/cell geometry columns, and
adds GiST indexes. The custom SQLAlchemy geometry type compiles to text only under SQLite so local
service tests do not require SpatiaLite.

Before staging migration, confirm the migration role can run:

```sql
CREATE EXTENSION IF NOT EXISTS postgis;
SELECT PostGIS_Version();
```

Do not precompute global cells. Load reviewed pilot region boundaries first, then generate cells only
inside those boundaries. Records with no authoritative coordinates retain `location_text` and an
`unresolved` spatial status.

## Adapter and sync rules

`SourceAdapter` accepts a bounded cursor/ETag request and returns an `AdapterBatch`. The explicit
registry is the allow-list; an adapter not registered in the process cannot run. Phase 1 registers
only `manual_snapshot`, a no-network adapter for controlled upload workflows.

The admin UI and operations console only create a `queued` sync run. They never call a provider,
parse a historical archive, or upload a large object inside the FastAPI request path. A later worker
increment will claim jobs in bounded batches and implement UAC/CAIC adapters after authoritative
contracts and rate limits are verified.

Raw bytes do not belong in PostgreSQL. Before a source record is marked normalized, the worker must
archive the original payload in OCI Object Storage and persist its bucket/key, checksum, content
type, size, adapter version, and normalization version in `source_records`.

## Admin control plane

Authenticated administrators receive:

- `/admin/data-sources`: connection state, source counts, queued syncs, job history, backup state,
  and disabled-by-default source registration.
- `/admin/data-inspector`: tenant-scoped search across provider IDs, UUIDs, callsigns, location text,
  transcripts, events, regions, and terrain cells.
- Existing operations console commands:
  - `source list`
  - `source show <id|slug>`
  - `source sync <id|slug>`
  - `sync list`
  - `inspect [source|event] <id|text>`
  - `database status`
  - `backup status`

Commands remain Python allow-list operations. There is no browser shell, command concatenation,
subprocess execution, or root access. New source creates, queued syncs, and successful operations
commands produce audit records.

## Validation and controlled rollout

GitHub Actions remain disabled. Run validation locally, then in an isolated staging database.

```bash
UV_CACHE_DIR=/tmp/terrasatch-uv-cache uv sync --frozen --extra dev
UV_CACHE_DIR=/tmp/terrasatch-uv-cache uv run ruff check src tests migrations
UV_CACHE_DIR=/tmp/terrasatch-uv-cache uv run python -m compileall -q src tests migrations
UV_CACHE_DIR=/tmp/terrasatch-uv-cache uv run pytest
UV_CACHE_DIR=/tmp/terrasatch-uv-cache uv run alembic heads
UV_CACHE_DIR=/tmp/terrasatch-uv-cache uv run alembic upgrade head --sql > /tmp/terrasatch-0007.sql
```

Staging sequence:

1. Take and verify a current logical backup.
2. Confirm PostGIS privilege and disk headroom.
3. Apply `0007` to staging.
4. Deploy the branch build to staging.
5. Validate admin login, CSRF, new screens, and allow-listed commands.
6. Replay the validated Edge transmission contract and confirm the same transmission, transcript,
   and operational event behavior.
7. Confirm Redis event publication and the UAC preview event/transcript reads.
8. Create a disabled manual source, enable it intentionally, and queue one empty sync.
9. Verify an audit row and backup visibility row can be inspected.
10. Observe staging before scheduling the production migration.

Do not merge or deploy to production until these checks are recorded on the draft PR.

## Backup and restore evidence

`backup_snapshots` is visibility, not backup execution. Backup jobs continue outside the public
application and report only non-secret state into this table.

The pilot recovery set is:

- PostgreSQL logical backup.
- OCI block-volume backup for the data host.
- OCI Object Storage versioning and retention for raw source payloads.
- A documented restore test with timestamp and result.

A backup is not considered healthy until a restore test has succeeded. Never add a browser command
that can delete backup generations or restore over production.

## OCI pilot topology and Bastion path

Keep the initial deployment consolidated:

- `ts-control-01`: Caddy, FastAPI, admin, worker, scheduler, Redis.
- `ts-data-01`: PostgreSQL/PostGIS and database volumes.
- Optional `ts-stage-01`: branch/staging validation.

Reserve unused VMs until measured load requires a split. Do not expose an unrestricted terminal in
`/admin`.

Target administration path:

```text
Windows PowerShell or WSL
  → OCI Bastion
  → private ts-control-01
  → private ts-data-01 when explicitly required
```

Example local SSH aliases after the Bastion session and private addresses are provisioned:

```sshconfig
Host terrasatch-bastion
  HostName <bastion-session-endpoint>
  User opc
  IdentityFile ~/.ssh/terrasatch-oracle.key

Host terrasatch-prod
  HostName <private-control-plane-ip>
  User ubuntu
  IdentityFile ~/.ssh/terrasatch-oracle.key
  ProxyJump terrasatch-bastion
  ServerAliveInterval 30
  ServerAliveCountMax 3
```

Provisioning the Bastion, changing OCI security lists, and moving public SSH are separate controlled
infrastructure changes and are not performed by this application migration.

## Deliberately deferred

- UAC, CAIC, Wyssen, weather, GIS, drone, and sensor network adapters.
- Historical bulk import execution and source-specific normalization.
- Object Storage upload client and retention automation.
- Worker queue claiming, retries, scheduling, and rate-limit policy.
- Automatic point-in-polygon and terrain-cell assignment.
- Event editing, reprocessing, cell reassignment, and data-quality resolution workflows.
- Edge heartbeat history.
- Backup execution and restore orchestration.
- OCI Bastion provisioning and public SSH removal.
- Forecast, weather-observation, and sensor-observation subtype tables.

These remain separate increments so the proven realtime path can be validated after each change.
