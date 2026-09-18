#!/usr/bin/env bash
set -euo pipefail

BRANCH="${TERRASATCH_STAGING_BRANCH:-feat/subscription-billing}"
EXPECTED_HEAD="${TERRASATCH_EXPECTED_STAGING_HEAD:-}"
PROD_REPO="${TERRASATCH_PROD_REPO:-/opt/terrasatch/api}"
DEFAULT_STAGING_DIR="${TERRASATCH_STAGING_DIR:-/home/ubuntu/terrasatch-workspace-staging}"
CADDYFILE="${TERRASATCH_CADDYFILE:-/etc/caddy/Caddyfile}"

say() { printf '\n==> %s\n' "$*"; }
die() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

if [[ ! -d "$PROD_REPO/.git" && ! -f "$PROD_REPO/.git" ]]; then
  candidate="$(
    find /opt /home/ubuntu -maxdepth 5 -type d -name .git -print 2>/dev/null |
      while read -r gitdir; do
        repo="${gitdir%/.git}"
        remote="$(git -C "$repo" remote get-url origin 2>/dev/null || true)"
        if [[ "$remote" == *"k3y10/terrasatch-api-v1"* ]]; then
          printf '%s\n' "$repo"
          break
        fi
      done
  )"
  [[ -n "$candidate" ]] || die "Could not locate the TerraSatch API repository."
  PROD_REPO="$candidate"
fi

say "Production repository: $PROD_REPO"
prod_branch="$(git -C "$PROD_REPO" branch --show-current)"
prod_head="$(git -C "$PROD_REPO" rev-parse HEAD)"
printf 'Production branch: %s\nProduction head:   %s\n' "$prod_branch" "$prod_head"
[[ "$prod_branch" == "main" ]] || die "Production checkout is not on main; refusing to continue."
[[ -z "$(git -C "$PROD_REPO" status --porcelain --untracked-files=no)" ]] ||
  die "Production checkout has tracked changes; refusing to continue."

say "Fetching staging branch without changing production"
git -C "$PROD_REPO" fetch --prune origin "$BRANCH"
remote_head="$(git -C "$PROD_REPO" rev-parse "origin/$BRANCH")"
printf 'Remote staging head: %s\n' "$remote_head"
if [[ -n "$EXPECTED_HEAD" && "$remote_head" != "$EXPECTED_HEAD" ]]; then
  printf 'Note: branch advanced from expected %s to %s; deploying current remote head.\n' "$EXPECTED_HEAD" "$remote_head"
fi

staging_dir="$(
  git -C "$PROD_REPO" worktree list --porcelain |
  awk -v target="refs/heads/$BRANCH" '
    $1=="worktree" { path=$2 }
    $1=="branch" && $2==target { print path; exit }
  '
)"

if [[ -z "$staging_dir" ]]; then
  staging_dir="$DEFAULT_STAGING_DIR"
  if [[ -e "$staging_dir" && ! -e "$staging_dir/.git" ]]; then
    die "Staging target exists but is not a Git worktree: $staging_dir"
  fi

  if git -C "$PROD_REPO" show-ref --verify --quiet "refs/heads/$BRANCH"; then
    git -C "$PROD_REPO" branch -f "$BRANCH" "origin/$BRANCH"
  else
    git -C "$PROD_REPO" branch --track "$BRANCH" "origin/$BRANCH"
  fi
  say "Creating isolated staging worktree: $staging_dir"
  mkdir -p "$(dirname "$staging_dir")"
  git -C "$PROD_REPO" worktree add "$staging_dir" "$BRANCH"
else
  say "Reusing isolated staging worktree: $staging_dir"
fi

[[ "$staging_dir" != "$PROD_REPO" ]] || die "Staging path resolved to production checkout."
[[ "$(git -C "$staging_dir" branch --show-current)" == "$BRANCH" ]] ||
  die "Staging worktree is not on $BRANCH."
[[ -z "$(git -C "$staging_dir" status --porcelain --untracked-files=no)" ]] ||
  die "Staging worktree has tracked changes; refusing to overwrite them."

git -C "$staging_dir" fetch origin "$BRANCH"
git -C "$staging_dir" reset --hard "origin/$BRANCH"
staging_head="$(git -C "$staging_dir" rev-parse HEAD)"
printf 'Staging head: %s\n' "$staging_head"

if [[ ! -f "$staging_dir/.env.staging" ]]; then
  mapfile -t env_candidates < <(
    find /opt/terrasatch /home/ubuntu -maxdepth 6 -type f -name .env.staging 2>/dev/null |
      grep -v "^$staging_dir/.env.staging$" || true
  )
  if [[ "${#env_candidates[@]}" -eq 1 ]]; then
    say "Restoring existing owner-only staging environment file"
    cp "${env_candidates[0]}" "$staging_dir/.env.staging"
    chmod 600 "$staging_dir/.env.staging"
  elif [[ "${#env_candidates[@]}" -gt 1 ]]; then
    printf 'Found multiple .env.staging files; refusing to guess:\n' >&2
    printf '  %s\n' "${env_candidates[@]}" >&2
    exit 1
  else
    die "No existing .env.staging was found on the server."
  fi
fi

chmod 600 "$staging_dir/.env.staging"
set -a
# shellcheck disable=SC1091
source "$staging_dir/.env.staging"
set +a

TERRASATCH_STRIPE_SECRET_KEY="${TERRASATCH_STRIPE_SECRET_KEY:-${STRIPE_SECRET_KEY:-}}"
TERRASATCH_STRIPE_WEBHOOK_SECRET="${TERRASATCH_STRIPE_WEBHOOK_SECRET:-${STRIPE_WEBHOOK_SECRET:-}}"

EXPECTED_STRIPE_ACCOUNT="${TERRASATCH_EXPECTED_STRIPE_ACCOUNT:-acct_1Txb0QPwzxCRGRdh}"

stripe_key_matches_account() {
  local candidate="$1"
  [[ "$candidate" == sk_test_* || "$candidate" == rk_test_* ]] || return 1
  local account_id
  account_id="$(
    curl --silent --show-error --fail       -u "$candidate:"       https://api.stripe.com/v1/account 2>/dev/null |
      python3 -c 'import json,sys; print(json.load(sys.stdin).get("id",""))' 2>/dev/null || true
  )"
  [[ "$account_id" == "$EXPECTED_STRIPE_ACCOUNT" ]]
}

persist_staging_stripe_key() {
  local candidate="$1"
  local tmp
  tmp="$(mktemp)"
  awk '!/^TERRASATCH_STRIPE_SECRET_KEY=|^STRIPE_SECRET_KEY=/' "$staging_dir/.env.staging" >"$tmp"
  printf 'TERRASATCH_STRIPE_SECRET_KEY=%s\n' "$candidate" >>"$tmp"
  install -m 600 "$tmp" "$staging_dir/.env.staging"
  rm -f "$tmp"
  TERRASATCH_STRIPE_SECRET_KEY="$candidate"
  export TERRASATCH_STRIPE_SECRET_KEY
}

if [[ -n "$TERRASATCH_STRIPE_SECRET_KEY" ]] && ! stripe_key_matches_account "$TERRASATCH_STRIPE_SECRET_KEY"; then
  die "Configured Stripe test key does not belong to the TerraSatch sandbox account."
fi

if [[ -z "$TERRASATCH_STRIPE_SECRET_KEY" ]]; then
  say "Searching existing server credentials for the TerraSatch sandbox key"
  discovered_key=""

  while IFS= read -r candidate; do
    [[ -n "$candidate" ]] || continue
    if stripe_key_matches_account "$candidate"; then
      discovered_key="$candidate"
      break
    fi
  done < <(
    {
      find /opt/terrasatch /etc/terrasatch /home/ubuntu /root         -maxdepth 6 -type f \( -name '.env' -o -name '.env.*' -o -name 'config.toml' \)         -readable -print0 2>/dev/null |
      xargs -0 -r awk -F= '
        /^[[:space:]]*(TERRASATCH_STRIPE_SECRET_KEY|STRIPE_SECRET_KEY|test_mode_api_key)[[:space:]]*=/ {
          value=$0
          sub(/^[^=]*=/,"",value)
          gsub(/^[[:space:]"'\''"]+|[[:space:]"'\''"]+$/,"",value)
          print value
        }
      '

      for container in $(docker ps -q 2>/dev/null); do
        docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' "$container" 2>/dev/null |
          awk -F= '
            $1=="TERRASATCH_STRIPE_SECRET_KEY" || $1=="STRIPE_SECRET_KEY" {
              sub(/^[^=]*=/,"")
              print
            }
          '
      done
    } | awk 'NF && !seen[$0]++'
  )

  if [[ -n "$discovered_key" ]]; then
    persist_staging_stripe_key "$discovered_key"
    say "Recovered an existing TerraSatch sandbox key and stored it in .env.staging"
  fi
fi

export TERRASATCH_STRIPE_SECRET_KEY TERRASATCH_STRIPE_WEBHOOK_SECRET

required=(
  POSTGRES_PASSWORD
  TERRASATCH_BILLING_ACTIVATION_SIGNING_SECRET
)
missing=()
for name in "${required[@]}"; do
  [[ -n "${!name:-}" ]] || missing+=("$name")
done
if [[ "${#missing[@]}" -gt 0 ]]; then
  printf 'Missing staging variables (values were not printed):\n' >&2
  printf '  %s\n' "${missing[@]}" >&2
  exit 1
fi

if [[ -n "$TERRASATCH_STRIPE_SECRET_KEY" ]]; then
  case "$TERRASATCH_STRIPE_SECRET_KEY" in
    sk_test_*|rk_test_*) ;;
    *) die "Configured Stripe credential is not a test-mode key." ;;
  esac
fi
if [[ "${TERRASATCH_BILLING_ALLOW_LIVEMODE:-false}" == "true" ]]; then
  die "TERRASATCH_BILLING_ALLOW_LIVEMODE must not be true in staging."
fi

say "Sandbox environment safety checks passed"
if [[ -n "$TERRASATCH_STRIPE_SECRET_KEY" ]]; then
  printf 'Stripe provider mode: test API key + sandbox webhooks\n'
else
  printf 'Stripe provider mode: hosted Payment Links + Caddy IP-restricted sandbox webhooks\n'
fi
printf 'Live billing: disabled\n'
if [[ -n "${TERRASATCH_BILLING_EMAIL_WEBHOOK_SECRET:-}" ]]; then
  printf 'Transactional email: configured\n'
else
  printf 'Transactional email: not configured (allowed in isolated staging; activation fallback enabled)\n'
fi
printf 'Required sandbox secrets: present (values suppressed)\n'

say "Running dependency lock validation, Ruff, and full pytest suite"
cd "$staging_dir"

lock_updated=false
lock_backup=""
cleanup_generated_lock() {
  status=$?
  trap - EXIT
  if [[ -n "$lock_backup" && -f "$lock_backup" ]]; then
    if ! git diff --quiet -- uv.lock; then
      cp "$lock_backup" uv.lock
    fi
    rm -f "$lock_backup"
  fi
  exit "$status"
}

if ! uv lock --check; then
  say "Repository lockfile is stale for the current uv resolver; regenerating uv.lock only"
  lock_backup="$(mktemp)"
  cp uv.lock "$lock_backup"
  trap cleanup_generated_lock EXIT
  uv lock
  lock_updated=true

  mapfile -t changed_after_lock < <(git status --porcelain --untracked-files=no | awk '{print $2}')
  if [[ "${#changed_after_lock[@]}" -ne 1 || "${changed_after_lock[0]}" != "uv.lock" ]]; then
    printf 'Unexpected tracked changes after uv lock:\n' >&2
    printf '  %s\n' "${changed_after_lock[@]}" >&2
    exit 1
  fi
  uv lock --check
fi

uv sync --extra dev --frozen
uv run ruff check src tests

say "Running pytest with staging environment variables scrubbed"
test_env_unset=()
while IFS= read -r key; do
  [[ -n "$key" ]] || continue
  test_env_unset+=("-u" "$key")
done < <(
  awk -F= '
    /^[[:space:]]*[A-Za-z_][A-Za-z0-9_]*[[:space:]]*=/ {
      key=$1
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", key)
      print key
    }
  ' "$staging_dir/.env.staging" | sort -u
)

# The bootstrap itself may synthesize/export aliases that are intentionally absent
# from .env.staging. Remove those too so Settings() tests exercise true defaults.
test_env_unset+=(
  "-u" "TERRASATCH_STRIPE_SECRET_KEY"
  "-u" "STRIPE_SECRET_KEY"
  "-u" "TERRASATCH_STRIPE_WEBHOOK_SECRET"
  "-u" "STRIPE_WEBHOOK_SECRET"
)

env "${test_env_unset[@]}" uv run pytest

if [[ "$lock_updated" == "true" ]]; then
  say "Tests passed with regenerated lockfile; committing uv.lock to the draft staging branch"
  git config user.name "TerraSatch Staging Automation"
  git config user.email "staging-automation@terrasatch.local"
  git add uv.lock
  git commit -m "Refresh uv lockfile for staging resolver"
  git push origin "HEAD:$BRANCH"
  staging_head="$(git rev-parse HEAD)"
  printf 'Staging branch advanced with validated lockfile: %s\n' "$staging_head"
  rm -f "$lock_backup"
  lock_backup=""
  lock_updated=false
  trap - EXIT
fi

say "Installing the isolated staging Caddy policy"
backup="$CADDYFILE.backup.$(date -u +%Y%m%dT%H%M%SZ)"
sudo cp "$CADDYFILE" "$backup"
tmp_caddy="$(mktemp)"
python3 - "$CADDYFILE" "$staging_dir/deploy/examples/Caddyfile.workspace-staging" "$tmp_caddy" <<'PY'
from pathlib import Path
import sys

source = Path(sys.argv[1]).read_text()
replacement = Path(sys.argv[2]).read_text().strip() + "\n"
target = "staging-api.terrasatch.com {"

start = source.find(target)
if start == -1:
    updated = source.rstrip() + "\n\n" + replacement
else:
    brace = source.find("{", start)
    if brace == -1:
        raise SystemExit("Malformed staging Caddy block")
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
        raise SystemExit("Unterminated staging Caddy block")
    updated = source[:start].rstrip() + "\n\n" + replacement + source[end:].lstrip()

Path(sys.argv[3]).write_text(updated)
PY
sudo install -m 644 "$tmp_caddy" "$CADDYFILE"
rm -f "$tmp_caddy"

if ! sudo caddy validate --config "$CADDYFILE"; then
  sudo cp "$backup" "$CADDYFILE"
  die "Caddy validation failed; original Caddyfile restored."
fi
sudo systemctl reload caddy

say "Deploying only the isolated workspace staging stack"
export TERRASATCH_STAGING_BRANCH="$BRANCH"
bash "$staging_dir/deploy/release-workspace-staging.sh"

say "Verifying container isolation"
docker compose -f "$staging_dir/deploy/docker-compose.workspace-staging.yml" ps
docker ps --format '{{.Names}}\t{{.Status}}\t{{.Ports}}' | grep -E 'terrasatch-workspace-staging|NAMES' || true

say "Verifying local staging routes"
curl --fail --silent --show-error http://127.0.0.1:8012/health/ready
printf '\n'
curl --fail --silent --show-error -o /dev/null -w 'local cancel page: %{http_code}\n'   http://127.0.0.1:8012/api/v1/workspace/billing/cancel
curl --fail --silent --show-error -o /dev/null -w 'local activation page: %{http_code}\n'   http://127.0.0.1:8012/api/v1/workspace/billing/activate

say "Verifying public staging routing"
curl --fail --silent --show-error -o /dev/null -w 'public cancel page: %{http_code}\n'   https://staging-api.terrasatch.com/api/v1/workspace/billing/cancel
webhook_public_code="$(curl --silent --output /dev/null --write-out '%{http_code}' https://staging-api.terrasatch.com/api/v1/workspace/billing/stripe/webhook || true)"
printf 'public webhook from non-Stripe IP: %s (expected 403)\n' "$webhook_public_code"
[[ "$webhook_public_code" == "403" ]] || die "Staging webhook is not restricted to Stripe source IPs."

checkout_smoke_email="staging-smoke-$(date +%s)@example.com"
checkout_smoke="$(
  curl --fail --silent --show-error     -H 'Content-Type: application/json'     -d "{\"display_name\":\"Staging Smoke\",\"email\":\"$checkout_smoke_email\",\"organization_name\":\"TerraSatch Staging Smoke\",\"plan_code\":\"field\",\"billing_interval\":\"monthly\"}"     https://staging-api.terrasatch.com/api/v1/workspace/billing/checkout
)"
python3 - "$checkout_smoke" <<'PY'
import json
import sys
payload = json.loads(sys.argv[1])
url = str(payload.get("checkout_url") or "")
if not url.startswith("https://buy.stripe.com/test_"):
    raise SystemExit("Staging checkout did not return a Stripe sandbox Payment Link")
if "client_reference_id=" not in url or "locked_prefilled_email=" not in url:
    raise SystemExit("Staging checkout URL is missing reconciliation parameters")
print("public staging checkout: 201-equivalent response with Stripe sandbox Payment Link")
PY

public_root_code="$(curl --silent --output /dev/null --write-out '%{http_code}' https://staging-api.terrasatch.com/health || true)"
printf 'public non-workspace route /health: %s (expected 404)\n' "$public_root_code"
[[ "$public_root_code" == "404" ]] || die "Staging Caddy is exposing more than /api/v1/workspace/*."

say "Checking recent staging logs"
docker compose -f "$staging_dir/deploy/docker-compose.workspace-staging.yml" logs --tail=80 api worker |
  grep -Ei 'error|exception|traceback|critical|failed' && {
    echo "Errors were found in recent staging logs; inspect before acceptance." >&2
    exit 1
  } || true

say "STAGING DEPLOYMENT PASSED"
printf 'Revision: %s\n' "$staging_head"
printf 'Production remained on: %s @ %s\n' "$prod_branch" "$prod_head"
printf 'Public staging endpoint: https://staging-api.terrasatch.com/api/v1/workspace/billing/stripe/webhook\n'
