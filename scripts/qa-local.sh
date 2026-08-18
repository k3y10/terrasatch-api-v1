#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON_BIN="${PYTHON_BIN:-python3}"
QA_CACHE_ROOT="${XDG_CACHE_HOME:-$HOME/.cache}/terrasatch"
VENV_DIR="${TERRASATCH_QA_VENV:-$QA_CACHE_ROOT/api-qa-venv}"

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

mkdir -p "$(dirname "$VENV_DIR")"
if [[ ! -d "$VENV_DIR" ]]; then
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1090
source "$VENV_DIR/bin/activate"

python -m pip install --upgrade pip
python -m pip install -e '.[dev]'

printf '\n[1/6] Ruff\n'
ruff check src tests

printf '\n[2/6] Compile/import smoke\n'
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

printf '\n[3/6] Full pytest + project coverage threshold\n'
pytest --cov=terrasatch --cov-report=term-missing --cov-report=xml

printf '\n[4/6] Migration graph smoke\n'
alembic heads

printf '\n[5/6] CLI/OpenAPI import smoke\n'
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

printf '\n[6/6] Provider fallback smoke\n'
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
