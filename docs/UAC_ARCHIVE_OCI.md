# UAC historical archive on Oracle OCI

The UAC partner workspace should not package the full Utah Avalanche Center CSV into the Vercel frontend. TerraSatch API can expose the public historical archive from a read-only file mounted into the existing Oracle Compose deployment.

## Data flow

```text
UAC public CSV export
  -> Oracle host persistent storage
  -> read-only Docker bind mount
  -> TerraSatch API /api/v1/uac/archive
  -> UAC Vercel preview /api/uac/history/[region]
  -> Events + Radio + map/cell evidence
```

Edge radio traffic remains on the existing canonical path:

```text
TerraSatch Edge
  -> Transmission
  -> Transcript
  -> TerraEngine / OperationalEvent
  -> PostgreSQL + Redis
  -> /api/v1/events + /api/v1/transcripts
  -> UAC workspace bridge
```

The historical archive does not replace or fork the live Edge pipeline. It is a separate read-only source used to replay historical UAC observations through the same workspace presentation model.

## Oracle host setup

Use a persistent directory outside the Git checkout:

```bash
sudo install -d -m 0750 /opt/terrasatch/data/uac
sudo cp /path/to/avalanches.csv /opt/terrasatch/data/uac/avalanches.csv
sudo chmod 0644 /opt/terrasatch/data/uac/avalanches.csv
```

Add these values to the owner-only deployment `.env` used by Compose:

```text
TERRASATCH_UAC_ARCHIVE_HOST_DIR=/opt/terrasatch/data/uac
TERRASATCH_UAC_ARCHIVE_PATH=/var/lib/terrasatch/uac/avalanches.csv
```

Compose mounts the host directory read-only into the API container. The CSV stays out of Git, the Docker build context, PostgreSQL, Redis, and Vercel.

## Validation before promotion

On an isolated checkout of `agent/uac-archive-oci-bridge`, run the normal local QA first:

```bash
uv sync --extra dev
uv run ruff check src tests
uv run pytest
```

Validate the Compose configuration and file mount without changing production traffic:

```bash
docker compose config
TERRASATCH_UAC_ARCHIVE_HOST_DIR=/opt/terrasatch/data/uac \
  docker compose run --rm api \
  python -c 'from pathlib import Path; p=Path("/var/lib/terrasatch/uac/avalanches.csv"); print(p.exists(), p.stat().st_size)'
```

After deploying the branch to an isolated API instance, verify:

```bash
curl -fsS 'https://<staging-api>/api/v1/uac/archive?region=salt-lake&limit=3'
curl -fsS 'https://<staging-api>/api/v1/uac/archive?region=salt-lake&trigger=human&limit=3'
curl -fsS 'https://<staging-api>/api/v1/uac/archive?region=salt-lake&from=2026-04-01&to=2026-05-31&limit=3'
```

Expected metadata includes:

```json
{
  "dataMode": "terrasatch-oci-archive",
  "archiveTotal": 10871
}
```

The exact `supportedTotal` can be lower than `archiveTotal` because the current UAC workspace supports the nine named forecast regions and intentionally excludes records that do not map cleanly to one of those regions or are missing required date/place fields.

## Connect the Vercel preview

The UAC workspace already prefers the TerraSatch archive endpoint. Point its preview environment at the isolated API with one of the existing server-side base URL variables:

```text
TERRASATCH_API_BASE_URL=https://<staging-api>
```

No public browser credential is required for the UAC archive endpoint because it serves public UAC historical data only. The existing Edge/API bridge still requires its server-side TerraSatch service credential to read tenant events/transcripts or ingest demo transmissions.

The frontend history route exposes `X-UAC-Archive-Source: terrasatch-api` when the OCI source is active. If the API source is unavailable it falls back to the verified local snapshot instead of breaking the workspace.

## Production boundary

Do not merge this branch or run `deploy/release-oracle.sh` against production until the isolated UAC workspace preview has been visually and functionally validated. The existing production API and existing Edge nodes should remain unchanged during preview QA.
