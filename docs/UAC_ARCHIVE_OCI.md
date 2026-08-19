# UAC historical archive on Oracle OCI

The UAC partner workspace should not package the full Utah Avalanche Center CSV into the Vercel frontend. TerraSatch API can expose the public historical archive from a read-only file mounted into an Oracle deployment.

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
  -> api.terrasatch.com
  -> Transmission
  -> Transcript
  -> TerraEngine / OperationalEvent
  -> PostgreSQL + Redis
  -> /api/v1/events + /api/v1/transcripts
  -> UAC workspace bridge
```

The historical archive does not replace or fork the live Edge pipeline. During preview QA it can run on a separate OCI instance or staging URL while live Edge traffic continues using the production TerraSatch API.

## Oracle host setup

Use a persistent directory outside the Git checkout:

```bash
sudo install -d -m 0750 /opt/terrasatch/data/uac
sudo cp /path/to/avalanches.csv /opt/terrasatch/data/uac/avalanches.csv
sudo chmod 0644 /opt/terrasatch/data/uac/avalanches.csv
```

The full production Compose stack supports these settings:

```text
TERRASATCH_UAC_ARCHIVE_HOST_DIR=/opt/terrasatch/data/uac
TERRASATCH_UAC_ARCHIVE_PATH=/var/lib/terrasatch/uac/avalanches.csv
```

The CSV stays out of Git, the Docker build context, PostgreSQL, Redis, and Vercel.

## Preferred preview: lightweight archive-only container

For isolated UAC QA, do not redirect the production API and do not start another PostgreSQL/Redis stack. On the spare OCI resource, check out `agent/uac-archive-oci-bridge` and run only the archive container:

```bash
cd /opt/terrasatch/api
TERRASATCH_UAC_ARCHIVE_HOST_DIR=/opt/terrasatch/data/uac \
  docker compose -f deploy/docker-compose.uac-archive-preview.yml up -d --build
```

The preview service binds to `127.0.0.1:8011` by default. Put Caddy/TLS in front of it for a staging hostname. The bind address and port can be changed without editing the Compose file:

```text
TERRASATCH_UAC_ARCHIVE_BIND_ADDRESS=127.0.0.1
TERRASATCH_UAC_ARCHIVE_PORT=8011
```

The archive-only service does not require its own PostgreSQL or Redis containers. Its container health check calls `/api/v1/uac/archive?limit=1`, so it validates that the CSV is mounted and parseable.

## Validation before promotion

Run local QA on the branch first:

```bash
uv sync --extra dev
uv run ruff check src tests
uv run pytest
```

Validate the archive-only Compose configuration:

```bash
TERRASATCH_UAC_ARCHIVE_HOST_DIR=/opt/terrasatch/data/uac \
  docker compose -f deploy/docker-compose.uac-archive-preview.yml config
```

Verify the mounted file without changing production traffic:

```bash
TERRASATCH_UAC_ARCHIVE_HOST_DIR=/opt/terrasatch/data/uac \
  docker compose -f deploy/docker-compose.uac-archive-preview.yml run --rm uac-archive \
  python -c 'from pathlib import Path; p=Path("/data/avalanches.csv"); print(p.exists(), p.stat().st_size)'
```

After the preview service is running, verify locally on the OCI host:

```bash
curl -fsS 'http://127.0.0.1:8011/api/v1/uac/archive?region=salt-lake&limit=3'
curl -fsS 'http://127.0.0.1:8011/api/v1/uac/archive?region=salt-lake&trigger=human&limit=3'
curl -fsS 'http://127.0.0.1:8011/api/v1/uac/archive?region=salt-lake&from=2026-04-01&to=2026-05-31&limit=3'
```

Expected metadata includes:

```json
{
  "dataMode": "terrasatch-oci-archive",
  "archiveTotal": 10871
}
```

The exact `supportedTotal` can be lower than `archiveTotal` because the current UAC workspace supports the nine named forecast regions and intentionally excludes records that do not map cleanly to one of those regions or are missing required date/place fields.

## Connect only the archive to the Vercel preview

Keep the existing operational API setting pointed at the live TerraSatch API so Edge event and transcript readback do not change:

```text
TERRASATCH_API_BASE_URL=https://api.terrasatch.com
```

Point only UAC history at the isolated OCI service:

```text
TERRASATCH_UAC_ARCHIVE_API_URL=https://<staging-archive-host>
```

The UAC history route checks `TERRASATCH_UAC_ARCHIVE_API_URL` first. If it is unset, it falls back to the ordinary TerraSatch API base URL. This lets the archive be validated independently without redirecting the existing Edge/API bridge.

No public browser credential is required for the UAC archive endpoint because it serves public UAC historical data only. The existing Edge/API bridge still requires its server-side TerraSatch service credential to read tenant events/transcripts or ingest demo transmissions.

The frontend history route exposes `X-UAC-Archive-Source: terrasatch-api` when the OCI source is active. If the API source is unavailable it falls back to the verified local snapshot instead of breaking the workspace.

## Production boundary

Do not merge this branch or run `deploy/release-oracle.sh` against production until the isolated UAC workspace preview has been visually and functionally validated. The existing production API and existing Edge nodes should remain unchanged during preview QA.
