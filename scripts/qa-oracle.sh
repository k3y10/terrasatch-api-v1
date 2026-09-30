#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 2
}

command -v docker >/dev/null 2>&1 || die "Docker is required."
docker compose version >/dev/null 2>&1 || die "Docker Compose v2 is required."

if command -v git >/dev/null 2>&1 && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  if [[ "${TERRASATCH_QA_ALLOW_DIRTY:-0}" != "1" ]]; then
    git diff --quiet || die "Working tree has unstaged changes. Commit/stash them or set TERRASATCH_QA_ALLOW_DIRTY=1."
    git diff --cached --quiet || die "Working tree has staged changes. Commit/stash them or set TERRASATCH_QA_ALLOW_DIRTY=1."
  fi
  printf 'Testing revision: %s\n' "$(git rev-parse --short=12 HEAD)"
fi

PROJECT="${TERRASATCH_QA_COMPOSE_PROJECT:-terrasatch-oracle-qa}"
KEEP="${TERRASATCH_QA_KEEP:-0}"
COMPOSE=(docker compose --project-name "$PROJECT" -f deploy/docker-compose.qa.yml)

cleanup() {
  status=$?
  if [[ "$KEEP" == "1" ]]; then
    printf '\nQA containers retained for inspection: %s\n' "$PROJECT"
    printf 'Clean them up with: docker compose --project-name %q -f deploy/docker-compose.qa.yml down -v --remove-orphans\n' "$PROJECT"
  else
    "${COMPOSE[@]}" down -v --remove-orphans >/dev/null 2>&1 || true
  fi
  exit "$status"
}
trap cleanup EXIT INT TERM

printf '\nTerraSatch Oracle-isolated full QA\n'
printf 'Compose project: %s\n' "$PROJECT"
printf 'Production containers, host ports, and production .env are not used.\n'

"${COMPOSE[@]}" down -v --remove-orphans >/dev/null 2>&1 || true
"${COMPOSE[@]}" config --quiet

printf '\nBuilding isolated QA image...\n'
"${COMPOSE[@]}" build qa

printf '\nRunning fresh PostGIS + Redis + full suite...\n'
"${COMPOSE[@]}" up --abort-on-container-exit --exit-code-from qa qa
