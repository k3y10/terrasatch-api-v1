#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${TERRASATCH_FEEDBACK_QA_BASE_URL:-https://staging-api.terrasatch.com}"
LOCAL_BASE_URL="${TERRASATCH_FEEDBACK_LOCAL_BASE_URL:-http://127.0.0.1:8013}"
COMPOSE_FILE="${TERRASATCH_FEEDBACK_COMPOSE_FILE:-deploy/docker-compose.feedback-staging.yml}"
SOURCE_ENV="${TERRASATCH_FEEDBACK_SOURCE_ENV:-/home/ubuntu/terrasatch-workspace-staging/.env.staging}"
DATABASE_NAME="${TERRASATCH_FEEDBACK_DATABASE_NAME:-terrasatch_feedback_staging}"
FORM_ID="OUTFIELD-CHECKIN"
EXPECTED_FORM_VERSION="3"
QA_COMMENT="__terrasatch_feedback_staging_qa__"

say() { printf '\n==> %s\n' "$*"; }
die() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

[[ -f "$COMPOSE_FILE" ]] || die "Missing staging compose file: $COMPOSE_FILE"
[[ -f "$SOURCE_ENV" ]] || die "Missing owner-only staging environment: $SOURCE_ENV"

set -a
# shellcheck disable=SC1090
source "$SOURCE_ENV"
set +a

[[ -n "${POSTGRES_PASSWORD:-}" ]] || die "POSTGRES_PASSWORD is missing from the staging environment."
[[ -n "${TERRASATCH_FEEDBACK_TURNSTILE_SECRET_KEY:-}" ]] ||
  die "A real staging Turnstile secret is required before acceptance QA."

say "Checking isolated feedback staging revision"
health_json="$(curl --fail --silent --show-error "$LOCAL_BASE_URL/health/ready")"
expected_revision="$(git rev-parse --short=12 HEAD)"
reported_revision="$(
  python3 -c 'import json,sys; print(json.load(sys.stdin).get("revision") or "")' <<<"$health_json"
)"
[[ "$reported_revision" == "$expected_revision" ]] ||
  die "Feedback API reports revision '$reported_revision'; expected '$expected_revision'."
printf 'Healthy revision: %s\n' "$reported_revision"

say "Checking isolated feedback database revision"
db_revision="$(
  docker compose -f "$COMPOSE_FILE" exec -T postgres     psql -U terrasatch -d "$DATABASE_NAME" -Atc     "SELECT version_num FROM alembic_version ORDER BY version_num DESC LIMIT 1;"
)"
[[ "$db_revision" == "0022_native_feedback" ]] ||
  die "Database revision is '$db_revision'; expected 0022_native_feedback."
printf 'Alembic revision: %s\n' "$db_revision"

say "Checking public adaptive form metadata"
metadata="$(curl --fail --silent --show-error "$BASE_URL/api/v1/feedback/forms/$FORM_ID")"
python3 -c '
import json
import sys
payload = json.load(sys.stdin)
expected = int(sys.argv[1])
assert payload["form_id"] == "OUTFIELD-CHECKIN", payload
assert payload["form_version"] == expected, payload
assert payload["anonymous_by_default"] is True, payload
assert payload["optional_contact"] is True, payload
assert payload["adaptive"] is True, payload
assert payload["estimated_seconds"] == 60, payload
assert payload["advertising_trackers"] is False, payload
' "$EXPECTED_FORM_VERSION" <<<"$metadata"
printf 'Public form metadata: OK\n'

say "Checking Turnstile is enforced at the API boundary"
missing_token_code="$(
  curl --silent --output /dev/null --write-out '%{http_code}'     -X POST     -H 'Content-Type: application/json'     -d '{
      "distribution_id": "DIRECT",
      "audience": "recreation",
      "activity_context": "backcountry_snow",
      "tools": ["phone_apps"],
      "primary_hassle": "nothing_major",
      "connectivity": "sometimes",
      "tool_follow_up": null,
      "pain_follow_up": null,
      "time_burden": null,
      "spend_band": "100_249",
      "concept_interest": "maybe",
      "questions_shown": ["audience", "activity_context", "tools", "connectivity", "primary_hassle", "spend_band", "concept_interest"],
      "started_at": "2026-09-28T12:00:00Z",
      "completion_seconds": 60,
      "comment": null
    }'     "$BASE_URL/api/v1/feedback/forms/$FORM_ID/responses" || true
)"
[[ "$missing_token_code" == "422" ]] ||
  die "Submission without Turnstile returned HTTP $missing_token_code; expected 422."
printf 'Missing Turnstile token: HTTP %s\n' "$missing_token_code"

bad_token_code="$(
  curl --silent --output /dev/null --write-out '%{http_code}' \
    -X POST \
    -H 'Content-Type: application/json' \
    -d '{
      "distribution_id": "DIRECT",
      "turnstile_token": "not-a-real-turnstile-token",
      "audience": "recreation",
      "activity_context": "backcountry_snow",
      "tools": ["phone_apps"],
      "primary_hassle": "nothing_major",
      "connectivity": "sometimes",
      "tool_follow_up": null,
      "pain_follow_up": null,
      "time_burden": null,
      "spend_band": "100_249",
      "concept_interest": "maybe",
      "contact_email": null,
      "contact_phone": null,
      "other_details": {},
      "questions_shown": ["audience", "activity_context", "tools", "connectivity", "primary_hassle", "spend_band", "concept_interest"],
      "started_at": "2026-09-29T12:00:00Z",
      "completion_seconds": 60,
      "comment": null
    }' \
    "$BASE_URL/api/v1/feedback/forms/$FORM_ID/responses" || true
)"
[[ "$bad_token_code" == "400" ]] ||
  die "Invalid Turnstile token returned HTTP $bad_token_code; expected 400."
printf 'Invalid Turnstile token: HTTP %s\n' "$bad_token_code"
printf 'Positive Turnstile submission: requires a browser-issued staging token.\n'

say "Checking founder analytics are not anonymous"
probe_org="00000000-0000-0000-0000-000000000000"
summary_code="$(
  curl --silent --output /dev/null --write-out '%{http_code}'     "$LOCAL_BASE_URL/api/v1/workspace/organizations/$probe_org/feedback/summary" || true
)"
case "$summary_code" in
  401|403) ;;
  *) die "Unauthenticated feedback summary returned HTTP $summary_code; expected 401 or 403." ;;
esac
printf 'Unauthenticated founder endpoint: HTTP %s\n' "$summary_code"

say "FEEDBACK STAGING ACCEPTANCE PASSED"
printf 'Form: %s v%s\n' "$FORM_ID" "$EXPECTED_FORM_VERSION"
printf 'Schema + adaptive branching: covered by focused API tests\n'
printf 'Turnstile: real staging secret enforced server-side\n'
printf 'Invalid token rejection: passed\n'
printf 'Positive browser submission: run from the Vercel preview\n'
