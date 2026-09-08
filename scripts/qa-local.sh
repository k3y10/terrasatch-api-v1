#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON_BIN="${PYTHON_BIN:-python3}"
QA_CACHE_ROOT="${XDG_CACHE_HOME:-$HOME/.cache}/terrasatch"
VENV_DIR="${TERRASATCH_QA_VENV:-$QA_CACHE_ROOT/api-qa-venv}"
COVERAGE_XML="$QA_CACHE_ROOT/api-changed-code-coverage.xml"

# QA must never inherit production connectivity or model execution settings.
export TERRASATCH_ENV=local
export TERRASATCH_ENVIRONMENT=local
export TERRASATCH_DEPLOYMENT_NAME=qa-local
export TERRASATCH_API_BASE_URL=http://127.0.0.1:18000
export TERRASATCH_DATABASE_URL=postgresql+asyncpg://terrasatch:terrasatch@127.0.0.1:55432/terrasatch_qa
export TERRASATCH_REDIS_URL=redis://127.0.0.1:56379/15
export TERRASATCH_INTELLIGENCE_PROVIDER=deterministic
unset TERRASATCH_ADMIN_EMAIL TERRASATCH_ADMIN_PASSWORD_HASH TERRASATCH_ADMIN_SESSION_SECRET || true

printf '\nTerraSatch API local QA\n'
printf 'Repository: %s\n' "$ROOT"
printf 'QA venv: %s\n' "$VENV_DIR"
printf 'Python: '
"$PYTHON_BIN" --version

"$PYTHON_BIN" - <<'PY'
import sys
if sys.version_info < (3, 12):
    raise SystemExit(f"Python 3.12+ required, found {sys.version}")
PY

mkdir -p "$QA_CACHE_ROOT"
if [[ ! -d "$VENV_DIR" ]]; then
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1090
source "$VENV_DIR/bin/activate"

python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
python -m pip check

git diff --check

printf '\n[1/8] Ruff\n'
ruff check src tests

printf '\n[2/8] Compile/import smoke\n'
python -m compileall -q src tests
python - <<'PY'
import terrasatch
from terrasatch.config import Settings
from terrasatch.intelligence.core import TerraEngine
from terrasatch.intelligence.providers import build_intelligence_provider
from terrasatch.intelligence.spatial import SpatialResolver
from terrasatch.radio.schemas import TransmissionCreateRequest

settings = Settings(intelligence_provider="deterministic")
provider = build_intelligence_provider(settings)
print(f"terrasatch {terrasatch.__version__} imports OK")
print(f"TerraEngine: {TerraEngine.__name__}")
print(f"Provider: {provider.__class__.__name__}")
print(f"Spatial resolver: {SpatialResolver.__name__}")
print(f"Transmission contract: {TransmissionCreateRequest.__name__}")
PY

printf '\n[3/8] Complete repository regression suite\n'
pytest

printf '\n[4/8] Satchy intelligence/STT contract coverage gate (>=80%%)\n'
pytest \
  tests/unit/test_intelligence.py \
  tests/unit/test_ollama_provider.py \
  tests/unit/test_spatial.py \
  tests/unit/test_transmission_stt_provenance.py \
  --cov=terrasatch.intelligence.core \
  --cov=terrasatch.intelligence.providers \
  --cov=terrasatch.intelligence.spatial \
  --cov=terrasatch.radio.schemas \
  --cov-report=term-missing \
  --cov-report="xml:$COVERAGE_XML" \
  --cov-fail-under=80

printf '\nNote: full-package coverage is not used as the 0.3 release gate because legacy admin/UI/CLI\nmodules predate the intelligence work and were not previously covered to the repository-wide 80%%\ntarget. The complete regression suite above still runs every repository test; the coverage gate\napplies to the TerraEngine/model/spatial/STT-contract surface introduced or materially changed.\n'

printf '\n[5/8] Edge command lifecycle coverage gate (>=80%%)\n'
COVERAGE_FILE="$QA_CACHE_ROOT/api-command-lifecycle.coverage" pytest \
  --cov=terrasatch.edge.command_service \
  --cov=terrasatch.edge.schemas \
  --cov=terrasatch.actions.state \
  --cov-report=term-missing \
  --cov-fail-under=80

printf '\n[6/8] Migration graph smoke\n'
alembic heads

printf '\n[7/8] CLI/OpenAPI import smoke\n'
terrasatch --help >/dev/null
python - <<'PY'
from terrasatch.config import Settings
from terrasatch.main import create_app
app = create_app(Settings(environment="local", deployment_name="qa-local"))
paths = app.openapi()["paths"]
required = {
    "/health",
    "/api/v1/transmissions",
    "/api/v1/events",
}
missing = required - set(paths)
if missing:
    raise SystemExit(f"Missing expected OpenAPI paths: {sorted(missing)}")
print("OpenAPI smoke OK")
PY

printf '\n[8/8] Deterministic fallback smoke\n'
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

printf '\nPASS: TerraSatch API full local QA completed successfully.\n'

