#!/usr/bin/env bash
set -euo pipefail

BRANCH="${TERRASATCH_FEEDBACK_STAGING_BRANCH:-feat/feedback-insights}"
COMPOSE_FILE="${TERRASATCH_FEEDBACK_COMPOSE_FILE:-deploy/docker-compose.feedback-staging.yml}"
SOURCE_ENV="${TERRASATCH_FEEDBACK_SOURCE_ENV:-/home/ubuntu/terrasatch-workspace-staging/.env.staging}"
CADDYFILE="${TERRASATCH_CADDYFILE:-/etc/caddy/Caddyfile}"
LOCAL_HEALTH="${TERRASATCH_FEEDBACK_LOCAL_HEALTH:-http://127.0.0.1:8013/health/ready}"
PUBLIC_FORM="${TERRASATCH_FEEDBACK_PUBLIC_FORM:-https://staging-api.terrasatch.com/api/v1/feedback/forms/OUTFIELD-CHECKIN}"

say() { printf '\n==> %s\n' "$*"; }
die() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

[[ "$BRANCH" != "main" ]] || die "Refusing feedback staging deployment from main."
[[ "$(git branch --show-current)" == "$BRANCH" ]] ||
  die "Expected branch '$BRANCH'; current branch is '$(git branch --show-current)'."
[[ -z "$(git status --porcelain --untracked-files=no)" ]] ||
  die "Tracked working tree has changes; commit or restore them first."
[[ -f "$COMPOSE_FILE" ]] || die "Missing $COMPOSE_FILE"
[[ -f "$SOURCE_ENV" ]] || die "Missing owner-only staging environment: $SOURCE_ENV"

set -a
# shellcheck disable=SC1090
source "$SOURCE_ENV"
set +a

[[ -n "${POSTGRES_PASSWORD:-}" ]] || die "POSTGRES_PASSWORD is missing from the staging environment."

export TERRASATCH_BUILD_SHA
TERRASATCH_BUILD_SHA="$(git rev-parse --short=12 HEAD)"
printf 'Feedback staging revision: %s\n' "$TERRASATCH_BUILD_SHA"

say "Running feedback-only code QA"
uv lock --check
uv sync --extra dev --frozen
uv run ruff check   src/terrasatch/feedback   src/terrasatch/config.py   src/terrasatch/main.py   tests/api/test_feedback.py
uv run pytest -q tests/api/test_feedback.py

heads="$(uv run alembic heads | sed '/^[[:space:]]*$/d')"
printf '%s\n' "$heads"
[[ "$heads" == "0022_native_feedback (head)" ]] ||
  die "Expected one feedback branch Alembic head: 0022_native_feedback."

bash -n deploy/deploy-feedback-staging.sh
bash -n deploy/accept-feedback-staging.sh

say "Building isolated feedback staging API"
docker compose -f "$COMPOSE_FILE" config >/dev/null
docker compose -f "$COMPOSE_FILE" build api
docker compose -f "$COMPOSE_FILE" up -d postgres redis
docker compose -f "$COMPOSE_FILE" run --rm api alembic upgrade head
docker compose -f "$COMPOSE_FILE" up -d --force-recreate api

say "Waiting for isolated feedback API"
health_file="$(mktemp)"
trap 'rm -f "$health_file"' EXIT
for attempt in $(seq 1 30); do
  if curl --fail --silent --show-error "$LOCAL_HEALTH" >"$health_file" 2>/dev/null; then
    reported_revision="$(
      python3 - "$health_file" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text())
print(str(payload.get("revision") or ""))
PY
    )"
    if [[ "$reported_revision" == "$TERRASATCH_BUILD_SHA" ]]; then
      cat "$health_file"
      printf '\n'
      break
    fi
  fi
  if [[ "$attempt" == "30" ]]; then
    docker compose -f "$COMPOSE_FILE" ps >&2
    docker compose -f "$COMPOSE_FILE" logs --tail=120 api >&2
    die "Feedback staging API did not become healthy at the expected revision."
  fi
  sleep 2
done

say "Routing only the public feedback path to isolated port 8013"
backup="$CADDYFILE.feedback-backup.$(date -u +%Y%m%dT%H%M%SZ)"
sudo cp "$CADDYFILE" "$backup"
tmp_caddy="$(mktemp)"

python3 - "$CADDYFILE" "$tmp_caddy" <<'PY'
from pathlib import Path
import re
import sys

source_path = Path(sys.argv[1])
target_path = Path(sys.argv[2])
source = source_path.read_text()
host = "staging-api.terrasatch.com {"

start = source.find(host)
if start == -1:
    raise SystemExit("staging-api.terrasatch.com block was not found")

brace = source.find("{", start)
depth = 0
end = None
for index in range(brace, len(source)):
    char = source[index]
    if char == "{":
        depth += 1
    elif char == "}":
        depth -= 1
        if depth == 0:
            end = index + 1
            break

if end is None:
    raise SystemExit("staging-api.terrasatch.com block is unterminated")

block = source[start:end]
route = """
    @feedback path /api/v1/feedback/*
    handle @feedback {
        reverse_proxy 127.0.0.1:8013
    }
"""

pattern = re.compile(
    r"""
\n[ \t]*@feedback[ \t]+path[ \t]+/api/v1/feedback/\*[ \t]*\n
[ \t]*handle[ \t]+@feedback[ \t]*\{[ \t]*\n
(?:.*\n)*?
[ \t]*\}[ \t]*\n
""",
    re.VERBOSE,
)

if pattern.search(block):
    block = pattern.sub("\n" + route.strip("\n") + "\n", block, count=1)
else:
    markers = (
        "\n    @workspace ",
        "\n    @portal ",
        "\n    handle {",
    )
    insert_at = None
    for marker in markers:
        position = block.find(marker)
        if position != -1:
            insert_at = position
            break
    if insert_at is None:
        insert_at = block.rfind("}")
    block = block[:insert_at] + "\n" + route + block[insert_at:]

updated = source[:start] + block + source[end:]
target_path.write_text(updated)
PY

sudo install -m 644 "$tmp_caddy" "$CADDYFILE"
rm -f "$tmp_caddy"

if ! sudo caddy validate --config "$CADDYFILE"; then
  sudo cp "$backup" "$CADDYFILE"
  die "Caddy validation failed; the previous configuration was restored."
fi
sudo systemctl reload caddy

say "Verifying public feedback route"
metadata="$(curl --fail --silent --show-error "$PUBLIC_FORM")"
python3 -c '
import json
import sys

payload = json.load(sys.stdin)
assert payload["form_id"] == "OUTFIELD-CHECKIN", payload
assert payload["form_version"] == 2, payload
assert payload["adaptive"] is True, payload
assert payload["anonymous_by_default"] is True, payload
assert payload["advertising_trackers"] is False, payload
' <<<"$metadata"

say "FEEDBACK-ONLY STAGING DEPLOYMENT READY"
printf 'Local API:  http://127.0.0.1:8013\n'
printf 'Public API: %s\n' "$PUBLIC_FORM"
printf 'Production was not modified.\n'
