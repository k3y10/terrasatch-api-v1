#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 2
}

if [[ -f .env && "${TERRASATCH_QA_ALLOW_ENV_FILE:-0}" != "1" ]]; then
  die "Refusing to run QA with a local .env present. Use the isolated Oracle QA harness."
fi

export TERRASATCH_ENV="${TERRASATCH_ENV:-local}"
export TERRASATCH_ENVIRONMENT="${TERRASATCH_ENVIRONMENT:-local}"
export TERRASATCH_DEPLOYMENT_NAME="${TERRASATCH_DEPLOYMENT_NAME:-qa}"
export TERRASATCH_API_BASE_URL="${TERRASATCH_API_BASE_URL:-http://127.0.0.1:18000}"
export TERRASATCH_INTELLIGENCE_PROVIDER="${TERRASATCH_INTELLIGENCE_PROVIDER:-deterministic}"
export TERRASATCH_BILLING_ENABLED=false
export TERRASATCH_BILLING_ALLOW_LIVEMODE=false

unset   TERRASATCH_ADMIN_EMAIL   TERRASATCH_ADMIN_PASSWORD_HASH   TERRASATCH_ADMIN_SESSION_SECRET   TERRASATCH_STRIPE_SECRET_KEY   STRIPE_SECRET_KEY   TERRASATCH_STRIPE_WEBHOOK_SECRET   STRIPE_WEBHOOK_SECRET   TERRASATCH_RESEND_API_KEY   RESEND_API_KEY   TERRASATCH_RESEND_WEBHOOK_SECRET   RESEND_WEBHOOK_SECRET   TERRASATCH_BILLING_EMAIL_WEBHOOK_SECRET   TERRASATCH_BILLING_ACTIVATION_SIGNING_SECRET   TERRASATCH_INTEGRATION_ENCRYPTION_KEY   TERRASATCH_INTEGRATION_PROVIDER_CONFIG_JSON   TERRASATCH_GOOGLE_OAUTH_CLIENT_SECRET   TERRASATCH_SLACK_OAUTH_CLIENT_SECRET   TERRASATCH_ARCGIS_OAUTH_CLIENT_SECRET   TERRASATCH_FEEDBACK_TURNSTILE_SECRET_KEY || true

case "${TERRASATCH_ENV}" in
  production)
    die "QA may not run with TERRASATCH_ENV=production."
    ;;
esac

[[ -n "${TERRASATCH_DATABASE_URL:-}" ]] || die "TERRASATCH_DATABASE_URL is required."
[[ -n "${TERRASATCH_REDIS_URL:-}" ]] || die "TERRASATCH_REDIS_URL is required."

if [[ "${TERRASATCH_QA_ALLOW_NON_QA_DATABASE:-0}" != "1" && "${TERRASATCH_DATABASE_URL}" != *"terrasatch_qa"* ]]; then
  die "QA database URL must target terrasatch_qa unless TERRASATCH_QA_ALLOW_NON_QA_DATABASE=1."
fi

printf '\nTerraSatch full QA suite\n'
printf 'Python: '
python --version
printf 'Deployment: %s\n' "$TERRASATCH_DEPLOYMENT_NAME"
printf 'Database: isolated QA target\n'
printf 'Redis: isolated QA target\n'

python - <<'PY'
import sys
if sys.version_info < (3, 12):
    raise SystemExit(f"Python 3.12+ required, found {sys.version}")
PY

uv pip check

printf '\n[1/10] Ruff\n'
ruff check src tests migrations

printf '\n[2/10] Compile/import smoke\n'
python -m compileall -q src tests migrations
python - <<'PY'
import terrasatch
from terrasatch.config import Settings
from terrasatch.intelligence.core import TerraEngine
from terrasatch.intelligence.providers import build_intelligence_provider
from terrasatch.intelligence.spatial import SpatialResolver
from terrasatch.radio.schemas import TransmissionCreateRequest
from terrasatch.satchy.models import SatchyRun, SatchyRunStep

settings = Settings()
if settings.is_production:
    raise SystemExit("Refusing QA with production settings")

provider = build_intelligence_provider(settings)
print(f"terrasatch {terrasatch.__version__} imports OK")
print(f"TerraEngine: {TerraEngine.__name__}")
print(f"Provider: {provider.__class__.__name__}")
print(f"Spatial resolver: {SpatialResolver.__name__}")
print(f"Transmission contract: {TransmissionCreateRequest.__name__}")
print(f"Satchy run models: {SatchyRun.__name__}, {SatchyRunStep.__name__}")
PY

printf '\n[3/10] Alembic single-head graph\n'
head_count="$(alembic heads | sed '/^[[:space:]]*$/d' | wc -l | tr -d ' ')"
[[ "$head_count" == "1" ]] || die "Expected exactly one Alembic head, found $head_count."
alembic heads

printf '\n[4/10] Fresh PostgreSQL migration to head\n'
alembic upgrade head
alembic current

printf '\n[5/10] Complete repository regression suite\n'
pytest

QA_CACHE_ROOT="${XDG_CACHE_HOME:-/tmp}/terrasatch"
mkdir -p "$QA_CACHE_ROOT"

printf '\n[6/10] Satchy intelligence/STT contract coverage gate (>=80%%)\n'
pytest   tests/unit/test_intelligence.py   tests/unit/test_ollama_provider.py   tests/unit/test_spatial.py   tests/unit/test_transmission_stt_provenance.py   --cov=terrasatch.intelligence.core   --cov=terrasatch.intelligence.providers   --cov=terrasatch.intelligence.spatial   --cov=terrasatch.radio.schemas   --cov-report=term-missing   --cov-report="xml:$QA_CACHE_ROOT/api-changed-code-coverage.xml"   --cov-fail-under=80

printf '\n[7/10] Edge command lifecycle coverage gate (>=80%%)\n'
COVERAGE_FILE="$QA_CACHE_ROOT/api-command-lifecycle.coverage" pytest   --cov=terrasatch.edge.command_service   --cov=terrasatch.edge.schemas   --cov=terrasatch.actions.state   --cov-report=term-missing   --cov-fail-under=80

printf '\n[8/10] CLI/OpenAPI smoke\n'
terrasatch --help >/dev/null
python - <<'PY'
from terrasatch.config import Settings
from terrasatch.main import create_app

app = create_app(Settings())
paths = app.openapi()["paths"]
required = {
    "/health",
    "/api/v1/transmissions",
    "/api/v1/events",
    "/api/v1/workspace/organizations/{organization_id}/runs",
    "/api/v1/workspace/organizations/{organization_id}/runs/{run_id}",
}
missing = required - set(paths)
if missing:
    raise SystemExit(f"Missing expected OpenAPI paths: {sorted(missing)}")
print("OpenAPI smoke OK")
PY

printf '\n[9/10] Deterministic fallback smoke\n'
python - <<'PY'
import asyncio
from terrasatch.config import Settings
from terrasatch.intelligence.providers import build_intelligence_provider
from terrasatch.intelligence.core import TerraEngine

async def main() -> None:
    settings = Settings(intelligence_provider="deterministic")
    engine = TerraEngine(provider=build_intelligence_provider(settings))
    events = await engine.process(
        text="Patrol 4 reports shooting cracks on the northeast aspect around 9,800 feet."
    )
    if not events:
        raise SystemExit("Deterministic fallback produced no event")
    print(f"Fallback event: {events[0].event_type.value} confidence={events[0].confidence}")

asyncio.run(main())
PY

printf '\n[10/10] Satchy run schema smoke\n'
python - <<'PY'
from terrasatch.satchy.schemas import SatchyRunResponse, SatchyRunStepResponse

assert "steps" in SatchyRunResponse.model_fields
assert "source_refs" in SatchyRunStepResponse.model_fields
assert "action_id" in SatchyRunStepResponse.model_fields
print("Satchy run schema smoke OK")
PY

printf '\nPASS: TerraSatch full QA suite completed successfully.\n'
