#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${TERRASATCH_REPO_DIR:-/opt/terrasatch/api}"
PUBLIC_HOST="${TERRASATCH_PUBLIC_HOST:-api.terrasatch.com}"
PUBLIC_BASE_URL="https://${PUBLIC_HOST}"
HEALTH_FILE="$(mktemp)"
trap 'rm -f "$HEALTH_FILE"' EXIT

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
# The runtime image intentionally runs as a non-root user and /app/src is not writable.
# Compile source in memory so the smoke check never tries to create __pycache__ beside source files.
docker compose run --rm api python -c "from pathlib import Path; files=list(Path('/app/src').rglob('*.py')); [compile(path.read_text(encoding='utf-8'), str(path), 'exec') for path in files]; print(f'Python source syntax OK ({len(files)} files)')"
docker compose run --rm api python -c "import terrasatch.main; print('FastAPI import OK')"
docker compose run --rm api terrasatch --help >/dev/null
docker compose run --rm api terrasatch simulate radio --help >/dev/null

echo "[6/8] Applying database migrations"
docker compose run --rm api alembic upgrade head

echo "[7/8] Recreating application services"
docker compose up -d --force-recreate api worker

wait_for_health() {
  local url="$1"
  local resolve_arg="${2:-}"
  local attempts="${3:-30}"
  local delay="${4:-2}"
  local count=1

  while (( count <= attempts )); do
    if [[ -n "$resolve_arg" ]]; then
      if curl --fail --silent --show-error --resolve "$resolve_arg" "$url" >"$HEALTH_FILE" 2>/dev/null; then
        return 0
      fi
    elif curl --fail --silent --show-error "$url" >"$HEALTH_FILE" 2>/dev/null; then
      return 0
    fi
    sleep "$delay"
    count=$((count + 1))
  done

  echo "Health check failed after ${attempts} attempts: ${url}" >&2
  return 1
}

read_revision() {
  python3 - "$HEALTH_FILE" <<'PY'
import json
import sys
from pathlib import Path
payload = json.loads(Path(sys.argv[1]).read_text())
print(payload.get("revision", "unknown"))
PY
}

echo "[8/8] Verifying FastAPI and Caddy/TLS health"
wait_for_health "http://127.0.0.1:8000/health/ready"
RUNNING_REVISION="$(read_revision)"

if [[ "$RUNNING_REVISION" != "$TERRASATCH_BUILD_SHA" ]]; then
  echo "Revision mismatch: expected ${TERRASATCH_BUILD_SHA}, API reports ${RUNNING_REVISION}" >&2
  exit 1
fi

# Test the real HTTPS/Caddy path locally while preserving hostname and TLS SNI.
# This avoids relying on whether OCI supports public-IP hairpin access from the VM.
wait_for_health "${PUBLIC_BASE_URL}/health/ready" "${PUBLIC_HOST}:443:127.0.0.1"
PUBLIC_REVISION="$(read_revision)"

if [[ "$PUBLIC_REVISION" != "$TERRASATCH_BUILD_SHA" ]]; then
  echo "Caddy revision mismatch: expected ${TERRASATCH_BUILD_SHA}, API reports ${PUBLIC_REVISION}" >&2
  exit 1
fi

docker compose ps

echo "TerraSatch release healthy: ${TERRASATCH_BUILD_SHA}"
echo "HTTPS route verified through Caddy for ${PUBLIC_HOST}"
