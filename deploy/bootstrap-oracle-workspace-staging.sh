#!/usr/bin/env bash
set -euo pipefail

BRANCH="${TERRASATCH_STAGING_BRANCH:-feat/subscription-billing}"
EXPECTED_HEAD="${TERRASATCH_EXPECTED_STAGING_HEAD:-fbbbc13945e5eb7dc446cb16767fb4784edb36de}"
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
export TERRASATCH_STRIPE_SECRET_KEY TERRASATCH_STRIPE_WEBHOOK_SECRET

required=(
  POSTGRES_PASSWORD
  TERRASATCH_STRIPE_SECRET_KEY
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

case "$TERRASATCH_STRIPE_SECRET_KEY" in
  sk_test_*|rk_test_*) ;;
  *) die "TERRASATCH_STRIPE_SECRET_KEY is not a Stripe test-mode key." ;;
esac
if [[ "${TERRASATCH_BILLING_ALLOW_LIVEMODE:-false}" == "true" ]]; then
  die "TERRASATCH_BILLING_ALLOW_LIVEMODE must not be true in staging."
fi

say "Sandbox environment safety checks passed"
printf 'Stripe key mode: test\n'
printf 'Live billing: disabled\n'
if [[ -n "${TERRASATCH_BILLING_EMAIL_WEBHOOK_SECRET:-}" ]]; then
  printf 'Transactional email: configured\n'
else
  printf 'Transactional email: not configured (allowed in isolated staging; activation fallback enabled)\n'
fi
printf 'Required sandbox secrets: present (values suppressed)\n'

say "Running locked dependency check, Ruff, and full pytest suite"
cd "$staging_dir"
uv lock --check
uv sync --extra dev --frozen
uv run ruff check src tests
uv run pytest

say "Ensuring isolated staging Caddy host exists"
if ! sudo grep -qF 'staging-api.terrasatch.com {' "$CADDYFILE"; then
  backup="$CADDYFILE.backup.$(date -u +%Y%m%dT%H%M%SZ)"
  sudo cp "$CADDYFILE" "$backup"
  printf '\n' | sudo tee -a "$CADDYFILE" >/dev/null
  sudo cat "$staging_dir/deploy/examples/Caddyfile.workspace-staging" |
    sudo tee -a "$CADDYFILE" >/dev/null
  if ! sudo caddy validate --config "$CADDYFILE"; then
    sudo cp "$backup" "$CADDYFILE"
    die "Caddy validation failed; original Caddyfile restored."
  fi
  sudo systemctl reload caddy
else
  sudo caddy validate --config "$CADDYFILE"
fi

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
curl --fail --silent --show-error -o /dev/null -w 'public webhook GET (expected 405): %{http_code}\n'   https://staging-api.terrasatch.com/api/v1/workspace/billing/stripe/webhook || true
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
