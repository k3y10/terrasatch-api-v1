#!/usr/bin/env bash
set -euo pipefail

STAGING_DIR="${TERRASATCH_STAGING_DIR:-/home/ubuntu/terrasatch-workspace-staging}"
ENV_FILE="${TERRASATCH_STAGING_ENV_FILE:-$STAGING_DIR/.env.staging}"
COMPOSE_FILE="${TERRASATCH_STAGING_COMPOSE_FILE:-$STAGING_DIR/deploy/docker-compose.workspace-staging.yml}"
RESEND_WEBHOOK_URL="https://staging-api.terrasatch.com/api/v1/workspace/billing/resend/webhook"
RESEND_WEBHOOK_ID="${TERRASATCH_RESEND_WEBHOOK_ID:-76225e17-36a9-4dc9-95a4-b28094a26d4d}"
RESEND_DOMAIN_ID="${TERRASATCH_RESEND_DOMAIN_ID:-}"
RESEND_DOMAIN_NAME="terrasatch.com"

say() { printf '\n==> %s\n' "$*"; }
die() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

[[ -d "$STAGING_DIR" ]] || die "Missing staging worktree: $STAGING_DIR"
[[ -f "$ENV_FILE" ]] || die "Missing staging environment file: $ENV_FILE"
[[ -f "$COMPOSE_FILE" ]] || die "Missing staging Compose file: $COMPOSE_FILE"
EXPECTED_BRANCH="${TERRASATCH_STAGING_BRANCH:-feat/subscription-billing}"
[[ "$(git -C "$STAGING_DIR" branch --show-current)" == "$EXPECTED_BRANCH" ]] ||
  die "Resend staging setup must run from the isolated staging worktree for $EXPECTED_BRANCH."

chmod 600 "$ENV_FILE"

say "Configure direct TerraSatch staging email through Resend"
printf 'Secrets are read without terminal echo and are never printed.\n'

read -r -s -p "Resend sending API key (re_...): " resend_api_key
printf '\n'
[[ -n "$resend_api_key" ]] || die "Resend sending API key is required."
[[ "$resend_api_key" == re_* ]] || die "Resend sending API key must use the expected re_ prefix."

read -r -s -p "Resend admin API key (Full Access, re_...): " resend_admin_api_key
printf '\n'
[[ -n "$resend_admin_api_key" ]] || die "Resend admin API key is required for webhook setup."
[[ "$resend_admin_api_key" == re_* ]] ||
  die "Resend admin API key must use the expected re_ prefix."

say "Checking the TerraSatch Resend domain"
domains_response="$(
  curl --silent --show-error --fail-with-body \
    -H "Authorization: Bearer $resend_admin_api_key" \
    "https://api.resend.com/domains"
)" || die "Unable to list Resend domains with the supplied admin key."

read -r discovered_domain_id domain_status sending_capability receiving_capability < <(
  python3 - "$domains_response" "$RESEND_DOMAIN_NAME" "$RESEND_DOMAIN_ID" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
expected_name = sys.argv[2].casefold()
configured_id = sys.argv[3].strip()
items = payload.get("data") or payload.get("domains") or []
if not isinstance(items, list):
    items = []

matches = [
    item for item in items
    if isinstance(item, dict)
    and str(item.get("name") or "").casefold() == expected_name
]
if configured_id:
    configured = [
        item for item in matches
        if str(item.get("id") or "") == configured_id
    ]
    if configured:
        matches = configured

if not matches:
    raise SystemExit("terrasatch.com was not found in the Resend team for this Full Access key")
if len(matches) > 1:
    raise SystemExit("multiple terrasatch.com domains were returned; set TERRASATCH_RESEND_DOMAIN_ID explicitly")

item = matches[0]
capabilities = item.get("capabilities") or {}
print(
    str(item.get("id") or ""),
    str(item.get("status") or ""),
    str(capabilities.get("sending") or ""),
    str(capabilities.get("receiving") or ""),
)
PY
) || die "Unable to resolve terrasatch.com from the current Resend team."

unset domains_response
RESEND_DOMAIN_ID="$discovered_domain_id"

[[ -n "$RESEND_DOMAIN_ID" ]] || die "Resend did not return a domain ID for terrasatch.com."

domain_ready=false
if [[ "$domain_status" == "verified" || "$sending_capability" == "enabled" ]]; then
  domain_ready=true
fi

if [[ "$domain_ready" != "true" ]]; then
  printf 'Current Resend domain status: %s (sending=%s, receiving=%s)\n' \
    "${domain_status:-unknown}" "${sending_capability:-unknown}" "${receiving_capability:-unknown}"
  printf 'Requesting verification because sending is not enabled yet.\n'

  curl --silent --show-error --fail-with-body \
    -X POST \
    -H "Authorization: Bearer $resend_admin_api_key" \
    -H 'Content-Type: application/json' \
    "https://api.resend.com/domains/$RESEND_DOMAIN_ID/verify" >/dev/null ||
    die "Resend rejected the domain verification request."

  for attempt in $(seq 1 12); do
    domain_response="$(
      curl --silent --show-error --fail-with-body \
        -H "Authorization: Bearer $resend_admin_api_key" \
        "https://api.resend.com/domains/$RESEND_DOMAIN_ID"
    )" || die "Unable to retrieve the TerraSatch Resend domain."

    read -r domain_name domain_status sending_capability receiving_capability < <(
      python3 - "$domain_response" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
capabilities = payload.get("capabilities") or {}
print(
    str(payload.get("name") or ""),
    str(payload.get("status") or ""),
    str(capabilities.get("sending") or ""),
    str(capabilities.get("receiving") or ""),
)
PY
    )
    unset domain_response

    [[ "$domain_name" == "$RESEND_DOMAIN_NAME" ]] ||
      die "Configured Resend domain ID does not resolve to terrasatch.com."

    if [[ "$domain_status" == "verified" || "$sending_capability" == "enabled" ]]; then
      domain_ready=true
      break
    fi
    [[ "$attempt" -lt 12 ]] && sleep 5
  done
fi

[[ "$domain_ready" == "true" ]] ||
  die "terrasatch.com exists in Resend but sending is not enabled yet."

printf 'Resend domain: terrasatch.com (status=%s, sending=%s, receiving=%s)\n' \
  "${domain_status:-unknown}" "${sending_capability:-unknown}" "${receiving_capability:-unknown}"

say "Ensuring the staging Resend webhook preserves billing events and receives inbound email"
webhook_response="$(
  curl --silent --show-error --fail-with-body \
    -H "Authorization: Bearer $resend_admin_api_key" \
    "https://api.resend.com/webhooks/$RESEND_WEBHOOK_ID"
)" || die "Unable to retrieve the configured Resend webhook."

webhook_update_payload="$(
  python3 - "$webhook_response" "$RESEND_WEBHOOK_URL" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
expected_endpoint = sys.argv[2]
required = [
    "email.sent",
    "email.delivered",
    "email.delivery_delayed",
    "email.bounced",
    "email.complained",
    "email.failed",
    "email.suppressed",
    "email.received",
]
existing = payload.get("events") or []
if not isinstance(existing, list):
    existing = []
events = []
for event in [*existing, *required]:
    if isinstance(event, str) and event and event not in events:
        events.append(event)
print(
    json.dumps(
        {
            "endpoint": expected_endpoint,
            "events": events,
            "status": "enabled",
        },
        separators=(",", ":"),
    )
)
PY
)"

curl --silent --show-error --fail-with-body \
  -X PATCH \
  -H "Authorization: Bearer $resend_admin_api_key" \
  -H 'Content-Type: application/json' \
  -d "$webhook_update_payload" \
  "https://api.resend.com/webhooks/$RESEND_WEBHOOK_ID" >/dev/null ||
  die "Unable to update the Resend webhook endpoint/events."

webhook_verify="$(
  curl --silent --show-error --fail-with-body \
    -H "Authorization: Bearer $resend_admin_api_key" \
    "https://api.resend.com/webhooks/$RESEND_WEBHOOK_ID"
)" || die "Unable to verify the updated Resend webhook."

python3 - "$webhook_verify" "$RESEND_WEBHOOK_URL" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
expected_endpoint = sys.argv[2]
required = {
    "email.sent",
    "email.delivered",
    "email.delivery_delayed",
    "email.bounced",
    "email.complained",
    "email.failed",
    "email.suppressed",
    "email.received",
}
events = set(payload.get("events") or [])
endpoint = str(payload.get("endpoint") or "")
status = str(payload.get("status") or "enabled")
missing = sorted(required - events)
if endpoint != expected_endpoint:
    raise SystemExit(f"Resend webhook endpoint mismatch: {endpoint}")
if missing:
    raise SystemExit("Resend webhook is missing required events: " + ", ".join(missing))
if status == "disabled":
    raise SystemExit("Resend webhook is disabled")
print("Resend webhook endpoint: staging workspace")
print("Billing delivery events: preserved")
print("Inbound email.received: enabled")
PY
unset webhook_response webhook_update_payload webhook_verify

say "Rotating the staging Resend webhook signing secret"
rotate_response="$(
  curl --silent --show-error --fail-with-body \
    -X POST \
    -H "Authorization: Bearer $resend_admin_api_key" \
    -H 'Content-Type: application/json' \
    "https://api.resend.com/webhooks/$RESEND_WEBHOOK_ID/signing-secret/rotate"
)" || die "Resend rejected the admin key or webhook signing-secret rotation."

resend_webhook_secret="$(
  python3 - "$rotate_response" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
secret = str(payload.get("signing_secret") or "").strip()
if not secret.startswith("whsec_"):
    raise SystemExit("Resend rotation response did not include a webhook signing secret")
print(secret)
PY
)"
unset rotate_response
[[ "$resend_webhook_secret" == whsec_* ]] ||
  die "Resend webhook signing-secret rotation did not return the expected secret."
printf 'Resend webhook signing secret rotated and captured without printing it.\n'

billing_from='TerraSatch Billing <billing@terrasatch.com>'
billing_reply_to='support@terrasatch.com'
printf 'Billing sender: %s\n' "$billing_from"
printf 'Billing reply-to: %s\n' "$billing_reply_to"

quote_env_value() {
  python3 - "$1" <<'PY'
import json
import sys

print(json.dumps(sys.argv[1]))
PY
}

tmp_env="$(mktemp)"
cleanup() {
  rm -f "$tmp_env"
  unset resend_api_key resend_admin_api_key resend_webhook_secret billing_from billing_reply_to
}
trap cleanup EXIT

awk '
  !/^TERRASATCH_RESEND_API_KEY=/ &&
  !/^TERRASATCH_RESEND_WEBHOOK_SECRET=/ &&
  !/^TERRASATCH_BILLING_FROM=/ &&
  !/^TERRASATCH_BILLING_REPLY_TO=/
' "$ENV_FILE" >"$tmp_env"

printf 'TERRASATCH_RESEND_API_KEY=%s\n' "$(quote_env_value "$resend_api_key")" >>"$tmp_env"
if [[ -n "$resend_webhook_secret" ]]; then
  printf 'TERRASATCH_RESEND_WEBHOOK_SECRET=%s\n' "$(quote_env_value "$resend_webhook_secret")" >>"$tmp_env"
fi
printf 'TERRASATCH_BILLING_FROM=%s\n' "$(quote_env_value "$billing_from")" >>"$tmp_env"
printf 'TERRASATCH_BILLING_REPLY_TO=%s\n' "$(quote_env_value "$billing_reply_to")" >>"$tmp_env"

install -m 600 "$tmp_env" "$ENV_FILE"

say "Validating staging configuration without printing secrets"
(
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a

  python3 - <<'PY'
import os

required = (
    "TERRASATCH_RESEND_API_KEY",
    "TERRASATCH_BILLING_FROM",
)
missing = [name for name in required if not os.environ.get(name, "").strip()]
if missing:
    raise SystemExit("Missing required Resend staging configuration: " + ", ".join(missing))

api_key = os.environ["TERRASATCH_RESEND_API_KEY"].strip()
if not api_key.startswith("re_"):
    raise SystemExit("Resend API key does not use the expected re_ prefix")

webhook = os.environ.get("TERRASATCH_RESEND_WEBHOOK_SECRET", "").strip()
if webhook and not webhook.startswith("whsec_"):
    raise SystemExit("Resend webhook secret does not use the expected whsec_ prefix")

billing_from = os.environ["TERRASATCH_BILLING_FROM"].strip()
if "@terrasatch.com" not in billing_from.casefold():
    raise SystemExit("Billing sender must use the verified terrasatch.com domain")

print("Direct Resend sender configuration: present")
print("Billing sender domain: terrasatch.com")
print("Resend webhook verification: " + ("configured" if webhook else "not configured"))
PY

  docker compose -f "$COMPOSE_FILE" config >/dev/null
)

say "Restarting only the isolated staging API and worker"
(
  cd "$STAGING_DIR"
  set -a
  # shellcheck disable=SC1091
  source "$ENV_FILE"
  set +a
  export TERRASATCH_BUILD_SHA="$(git rev-parse --short=12 HEAD)"
  docker compose -f "$COMPOSE_FILE" up -d --force-recreate api worker
)

say "Waiting for staging API health"
for attempt in $(seq 1 30); do
  if curl --fail --silent --show-error     http://127.0.0.1:8012/health/ready >/tmp/terrasatch-resend-staging-health.json 2>/dev/null; then
    cat /tmp/terrasatch-resend-staging-health.json
    printf '\n'
    break
  fi
  if [[ "$attempt" -eq 30 ]]; then
    die "Staging API did not become healthy after Resend configuration."
  fi
  sleep 2
done

say "Verifying Resend webhook gate"
resend_code="$(
  curl --silent --output /dev/null --write-out '%{http_code}'     -X POST     -H 'Content-Type: application/json'     -d '{}'     "$RESEND_WEBHOOK_URL" || true
)"

if [[ -n "$resend_webhook_secret" ]]; then
  printf 'Unsigned Resend webhook request: %s (expected 400)\n' "$resend_code"
  [[ "$resend_code" == "400" ]] ||
    die "Configured Resend webhook did not reject an unsigned request."
else
  printf 'Resend webhook without signing secret: %s (expected 404)\n' "$resend_code"
  [[ "$resend_code" == "404" ]] ||
    die "Resend webhook should remain disabled until its signing secret is configured."
fi

say "RESEND STAGING CONFIGURATION PASSED"
printf 'Resend domain: %s (%s)\n' "$RESEND_DOMAIN_NAME" "$RESEND_DOMAIN_ID"
printf 'Resend webhook: %s\n' "$RESEND_WEBHOOK_ID"
printf 'Webhook URL: %s\n' "$RESEND_WEBHOOK_URL"
printf 'Admin key was used only for setup and was not persisted.\n'
printf 'Billing sender: TerraSatch Billing <billing@terrasatch.com>\n'
printf 'Live Stripe billing remains disabled.\n'
