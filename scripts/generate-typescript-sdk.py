#!/usr/bin/env python3
"""Regenerate @terrasatch/sdk declarations from the canonical FastAPI OpenAPI document."""

from pathlib import Path

from terrasatch.config import Settings
from terrasatch.main import create_app
from terrasatch.sdk.typescript import render_typescript_declarations

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "sdk" / "typescript" / "index.d.ts"


def main() -> None:
    app = create_app(
        Settings(
            environment="local",
            deployment_name="sdk-generation",
            api_base_url="http://sdk.invalid",
            intelligence_provider="deterministic",
        )
    )
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(render_typescript_declarations(app.openapi()), encoding="utf-8")
    print(f"Wrote {TARGET.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
