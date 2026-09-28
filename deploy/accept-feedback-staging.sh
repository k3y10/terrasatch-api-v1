#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${TERRASATCH_FEEDBACK_QA_BASE_URL:-https://staging-api.terrasatch.com}"
LOCAL_BASE_URL="${TERRASATCH_FEEDBACK_LOCAL_BASE_URL:-http://127.0.0.1:8013}"
COMPOSE_FILE="${TERRASATCH_FEEDBACK_COMPOSE_FILE:-deploy/docker-compose.feedback-staging.yml}"
DATABASE_NAME="${TERRASATCH_FEEDBACK_DATABASE_NAME:-terrasatch_feedback_staging}"
FORM_ID="OUTFIELD-CHECKIN"
EXPECTED_FORM_VERSION="2"
QA_COMMENT="__terrasatch_feedback_staging_qa__"
DUMMY_TOKEN="XXXX.DUMMY.TOKEN.XXXX"

say() { printf '\n==> %s\n' "$*"; }
die() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

[[ -f "$COMPOSE_FILE" ]] || die "Missing staging compose file: $COMPOSE_FILE"

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
  curl --silent --output /dev/null --write-out '%{http_code}'     -X POST     -H 'Content-Type: application/json'     -d '{
      "distribution_id": "DIRECT",
      "turnstile_token": "not-a-valid-test-token",
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
[[ "$bad_token_code" == "400" ]] ||
  die "Invalid Turnstile token returned HTTP $bad_token_code; expected 400."
printf 'Invalid Turnstile token: HTTP %s\n' "$bad_token_code"

say "Submitting one disposable adaptive QA response"
response="$(
  curl --fail --silent --show-error     -X POST     -H 'Content-Type: application/json'     -d "{
      \"distribution_id\": \"QA-STAGING-UNREGISTERED\",
      \"turnstile_token\": \"$DUMMY_TOKEN\",
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
  docker compose -f "$COMPOSE_FILE" exec -T postgres     psql -v ON_ERROR_STOP=1 -U terrasatch -d "$DATABASE_NAME"     -c "DELETE FROM feedback_survey_responses WHERE id = '$response_id'::uuid;"     >/dev/null 2>&1 || true
}
trap cleanup EXIT

say "Verifying persisted discovery path"
persisted="$(
  docker compose -f "$COMPOSE_FILE" exec -T postgres     psql -U terrasatch -d "$DATABASE_NAME" -Atc     "SELECT
       form_id || '|' ||
       form_version || '|' ||
       distribution_id || '|' ||
       COALESCE(answers->>'completion_seconds', '') || '|' ||
       CASE WHEN answers ? 'questions_shown' THEN 'shown' ELSE 'missing' END || '|' ||
       CASE WHEN answers ? 'branch_path' THEN 'branched' ELSE 'missing' END || '|' ||
       CASE WHEN answers ? 'email' THEN 'email-present' ELSE 'no-email' END || '|' ||
       COALESCE(comment, '')
     FROM feedback_survey_responses
     WHERE id = '$response_id'::uuid;"
)"
expected_row="$FORM_ID|$EXPECTED_FORM_VERSION|DIRECT|60|shown|branched|no-email|$QA_COMMENT"
[[ "$persisted" == "$expected_row" ]] ||
  die "Persisted adaptive response did not match the expected identity/path tuple."
printf 'Persisted response: %s\n' "$response_id"

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

say "Removing disposable QA response"
cleanup
trap - EXIT

remaining="$(
  docker compose -f "$COMPOSE_FILE" exec -T postgres     psql -U terrasatch -d "$DATABASE_NAME" -Atc     "SELECT COUNT(*) FROM feedback_survey_responses WHERE id = '$response_id'::uuid;"
)"
[[ "$remaining" == "0" ]] || die "Disposable QA response was not removed."

say "FEEDBACK STAGING ACCEPTANCE PASSED"
printf 'Form: %s v%s\n' "$FORM_ID" "$EXPECTED_FORM_VERSION"
printf 'Adaptive branching: persisted\n'
printf 'Turnstile: enforced server-side\n'
printf 'Attribution: unknown IDs -> DIRECT\n'
printf 'QA response removed: %s\n' "$response_id"
