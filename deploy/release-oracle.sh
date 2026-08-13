#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${TERRASATCH_REPO_DIR:-/opt/terrasatch/api}"
PUBLIC_BASE_URL="${TERRASATCH_PUBLIC_BASE_URL:-https://api.terrasatch.com}"

cd "$REPO_DIR"

if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "Refusing deployment: tracked working tree has uncommitted changes." >&2
  exit 1
fi

echo "[1/8] Updating main"
git fetch origin
git checkout main
git pull --ff-only origin main

export TERRASATCH_BUILD_SHA="$(git rev-parse --short=12 HEAD)"
echo "Deploying TerraSatch revision: ${TERRASATCH_BUILD_SHA}"

echo "[2/8] Validating Compose configuration"
docker compose config >/dev/null

echo "[3/8] Starting stateful dependencies"
docker compose up -d postgres redis

echo "[4/8] Building API and worker images"
docker compose build api worker

echo "[5/8] Running import and CLI smoke checks"
docker compose run --rm api python -m compileall -q /app/src
docker compose run --rm api python -c "import terrasatch.main; print('FastAPI import OK')"
docker compose run --rm api terrasatch --help >/dev/null
docker compose run --rm api terrasatch simulate radio --help >/dev/null

echo "[6/8] Applying database migrations"
docker compose run --rm api alembic upgrade head

echo "[7/8] Recreating application services"
docker compose up -d --force-recreate api worker

wait_for_health() {
  local url="$1"
  local attempts="${2:-30}"
  local delay="${3:-2}"
  local count=1

  while (( count <= attempts )); do
    if curl --fail --silent --show-error "$url" >/tmp/terrasatch-health.json 2>/dev/null; then
      return 0
    fi
    sleep "$delay"
    count=$((count + 1))
  done

  echo "Health check failed after ${attempts} attempts: ${url}" >&2
  return 1
}

echo "[8/8] Verifying internal and public health"
wait_for_health "http://127.0.0.1:8000/health/ready"

RUNNING_REVISION="$(python3 - <<'PY'
import json
from pathlib import Path
payload = json.loads(Path('/tmp/terrasatch-health.json').read_text())
print(payload.get('revision', 'unknown'))
PY
)"

if [[ "$RUNNING_REVISION" != "$TERRASATCH_BUILD_SHA" ]]; then
  echo "Revision mismatch: expected ${TERRASATCH_BUILD_SHA}, API reports ${RUNNING_REVISION}" >&2
  exit 1
fi

wait_for_health "${PUBLIC_BASE_URL}/health/ready"

PUBLIC_REVISION="$(python3 - <<'PY'
import json
from pathlib import Path
payload = json.loads(Path('/tmp/terrasatch-health.json').read_text())
print(payload.get('revision', 'unknown'))
PY
)"

if [[ "$PUBLIC_REVISION" != "$TERRASATCH_BUILD_SHA" ]]; then
  echo "Public revision mismatch: expected ${TERRASATCH_BUILD_SHA}, API reports ${PUBLIC_REVISION}" >&2
  exit 1
fi

docker compose ps

echo "TerraSatch release healthy: ${TERRASATCH_BUILD_SHA}"
echo "Public API: ${PUBLIC_BASE_URL}"
