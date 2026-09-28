#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${TERRASATCH_FEEDBACK_QA_BASE_URL:-https://staging-api.terrasatch.com}"
COMPOSE_FILE="${TERRASATCH_STAGING_COMPOSE_FILE:-deploy/docker-compose.workspace-staging.yml}"
FORM_ID="OUTFIELD-CHECKIN"
EXPECTED_FORM_VERSION="2"
QA_COMMENT="__terrasatch_feedback_staging_qa__"

say() { printf '\n==> %s\n' "$*"; }
die() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

[[ -f "$COMPOSE_FILE" ]] || die "Missing staging compose file: $COMPOSE_FILE"

say "Checking local staging revision"
health_json="$(curl --fail --silent --show-error http://127.0.0.1:8012/health/ready)"
expected_revision="$(git rev-parse --short=12 HEAD)"
reported_revision="$(
  python3 -c 'import json,sys; print(json.load(sys.stdin).get("revision") or "")' <<<"$health_json"
)"
[[ "$reported_revision" == "$expected_revision" ]] ||
  die "Staging API reports revision '$reported_revision'; expected '$expected_revision'."
printf 'Healthy revision: %s\n' "$reported_revision"

say "Checking migrated database revision"
db_revision="$(
  docker compose -f "$COMPOSE_FILE" exec -T postgres     psql -U terrasatch -d terrasatch_staging -Atc     "SELECT version_num FROM alembic_version ORDER BY version_num DESC LIMIT 1;"
)"
[[ "$db_revision" == "0022_native_feedback" ]] ||
  die "Database revision is '$db_revision'; expected 0022_native_feedback."
printf 'Alembic revision: %s\n' "$db_revision"

say "Checking public form metadata"
metadata="$(curl --fail --silent --show-error "$BASE_URL/api/v1/feedback/forms/$FORM_ID")"
python3 -c '
import json
import sys
payload = json.load(sys.stdin)
expected = int(sys.argv[1])
assert payload["form_id"] == "OUTFIELD-CHECKIN", payload
assert payload["form_version"] == expected, payload
assert payload["anonymous_by_default"] is True, payload
assert payload["adaptive"] is True, payload
assert payload["estimated_seconds"] == 60, payload
assert payload["advertising_trackers"] is False, payload
' "$EXPECTED_FORM_VERSION" <<<"$metadata"
printf 'Public form metadata: OK\n'

say "Submitting one disposable public QA response"
response="$(
  curl --fail --silent --show-error     -X POST     -H 'Content-Type: application/json'     -d "{
      \"distribution_id\": \"QA-STAGING-UNREGISTERED\",
      \"turnstile_token\": \"XXXX.DUMMY.TOKEN.XXXX\",
      \"audience\": \"recreation\",
      \"activity_context\": \"backcountry_snow\",
      \"tools\": [\"phone_apps\", \"radio\"],
      \"primary_hassle\": \"losing_service\",
      \"connectivity\": \"sometimes\",
      \"tool_follow_up\": \"radio_only\",
      \"pain_follow_up\": \"communicate\",
      \"time_burden\": null,
      \"spend_band\": \"100_249\",
      \"concept_interest\": \"would_try\",
      \"questions_shown\": [\"audience\", \"activity_context\", \"tools\", \"connectivity\", \"primary_hassle\", \"tool_follow_up\", \"pain_follow_up\", \"spend_band\", \"concept_interest\"],
      \"started_at\": \"2026-09-28T12:00:00Z\",
      \"completion_seconds\": 60,
      \"comment\": \"$QA_COMMENT\"
    }"     "$BASE_URL/api/v1/feedback/forms/$FORM_ID/responses"
)"

read -r response_id returned_form returned_version returned_distribution < <(
  python3 -c '
import json
import sys
payload = json.load(sys.stdin)
assert payload["accepted"] is True, payload
print(
    payload["response_id"],
    payload["form_id"],
    payload["form_version"],
    payload["distribution_id"],
)
' <<<"$response"
)

[[ "$returned_form" == "$FORM_ID" ]] || die "Unexpected form ID: $returned_form"
[[ "$returned_version" == "$EXPECTED_FORM_VERSION" ]] ||
  die "Unexpected form version: $returned_version"
[[ "$returned_distribution" == "DIRECT" ]] ||
  die "Unregistered distribution should resolve to DIRECT, got: $returned_distribution"

cleanup() {
  docker compose -f "$COMPOSE_FILE" exec -T postgres     psql -v ON_ERROR_STOP=1 -U terrasatch -d terrasatch_staging     -c "DELETE FROM feedback_survey_responses WHERE id = '$response_id'::uuid;"     >/dev/null 2>&1 || true
}
trap cleanup EXIT

say "Verifying persisted response"
persisted="$(
  docker compose -f "$COMPOSE_FILE" exec -T postgres     psql -U terrasatch -d terrasatch_staging -Atc     "SELECT form_id || '|' || form_version || '|' || distribution_id || '|' || COALESCE(comment, '')
     FROM feedback_survey_responses
     WHERE id = '$response_id'::uuid;"
)"
expected_row="$FORM_ID|$EXPECTED_FORM_VERSION|DIRECT|$QA_COMMENT"
[[ "$persisted" == "$expected_row" ]] ||
  die "Persisted response did not match the expected first-party identity tuple."
printf 'Persisted response: %s\n' "$response_id"

say "Checking founding-team endpoints are not public"
probe_org="00000000-0000-0000-0000-000000000000"
summary_code="$(
  curl --silent --output /dev/null --write-out '%{http_code}'     "$BASE_URL/api/v1/workspace/organizations/$probe_org/feedback/summary" || true
)"
case "$summary_code" in
  401|403) ;;
  *) die "Unauthenticated feedback summary returned HTTP $summary_code; expected 401 or 403." ;;
esac
printf 'Unauthenticated founder endpoint: HTTP %s\n' "$summary_code"

say "Removing disposable QA response"
cleanup
trap - EXIT

remaining="$(
  docker compose -f "$COMPOSE_FILE" exec -T postgres     psql -U terrasatch -d terrasatch_staging -Atc     "SELECT COUNT(*) FROM feedback_survey_responses WHERE id = '$response_id'::uuid;"
)"
[[ "$remaining" == "0" ]] || die "Disposable QA response was not removed."

say "FEEDBACK STAGING ACCEPTANCE PASSED"
printf 'Form: %s v%s\n' "$FORM_ID" "$EXPECTED_FORM_VERSION"
printf 'Attribution: TerraSatch-owned distribution IDs, unknown IDs -> DIRECT\n'
printf 'QA response removed: %s\n' "$response_id"
