#!/usr/bin/env bash
set -euo pipefail

BRANCH="${TERRASATCH_STAGING_BRANCH:-feat/subscription-billing}"
COMPOSE_FILE="deploy/docker-compose.workspace-staging.yml"
ENV_FILE=".env.staging"
HEALTH_URL="${TERRASATCH_STAGING_HEALTH_URL:-http://127.0.0.1:8012/health/ready}"

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

if [[ "$BRANCH" == "main" ]]; then
  echo "Refusing staging deployment from main." >&2
  exit 1
fi

if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
  echo "Refusing staging deployment: tracked working tree has changes." >&2
  exit 1
fi

current_branch="$(git branch --show-current)"
if [[ "$current_branch" != "$BRANCH" ]]; then
  echo "Refusing staging deployment from branch '$current_branch'; expected '$BRANCH'." >&2
  echo "Run this script from the isolated staging worktree, never the production main checkout." >&2
  exit 1
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE. Restore the owner-only staging environment file before deployment." >&2
  exit 1
fi

git fetch origin "$BRANCH"
git merge --ff-only "origin/$BRANCH"

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

export TERRASATCH_BUILD_SHA="$(git rev-parse --short=12 HEAD)"
echo "Deploying isolated TerraSatch workspace staging revision: $TERRASATCH_BUILD_SHA"

docker compose -f "$COMPOSE_FILE" config >/dev/null
docker compose -f "$COMPOSE_FILE" build api worker
docker compose -f "$COMPOSE_FILE" run --rm api alembic upgrade head
docker compose -f "$COMPOSE_FILE" up -d --force-recreate api worker

for attempt in $(seq 1 30); do
  if curl --fail --silent --show-error "$HEALTH_URL" >/tmp/terrasatch-workspace-staging-health.json; then
    reported_revision="$(
      python3 - <<'PY'
import json
from pathlib import Path

try:
    payload = json.loads(Path("/tmp/terrasatch-workspace-staging-health.json").read_text())
except (OSError, json.JSONDecodeError):
    print("")
else:
    print(str(payload.get("revision") or ""))
PY
    )"
    if [[ "$reported_revision" == "$TERRASATCH_BUILD_SHA" ]]; then
      cat /tmp/terrasatch-workspace-staging-health.json
      echo
      echo "Workspace staging is healthy at revision $TERRASATCH_BUILD_SHA"
      exit 0
    fi
    echo "Staging health is up but reports revision '$reported_revision'; waiting for $TERRASATCH_BUILD_SHA." >&2
  fi
  sleep 2
done

echo "Workspace staging did not become healthy." >&2
docker compose -f "$COMPOSE_FILE" ps >&2
docker compose -f "$COMPOSE_FILE" logs --tail=100 api worker >&2
exit 1
