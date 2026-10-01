"""OpenAPI and runtime contract gates for the shared TypeScript SDK."""

import json
from pathlib import Path

from terrasatch.config import Settings
from terrasatch.main import create_app
from terrasatch.sdk.typescript import render_typescript_declarations

ROOT = Path(__file__).resolve().parents[2]
SDK_JS = ROOT / "sdk" / "typescript" / "index.js"
SDK_DTS = ROOT / "sdk" / "typescript" / "index.d.ts"
PACKAGE_JSON = ROOT / "package.json"


def _openapi() -> dict[str, object]:
    return create_app(
        Settings(
            environment="local",
            deployment_name="typescript-sdk-contract",
            api_base_url="http://testserver",
            intelligence_provider="deterministic",
        )
    ).openapi()


def test_workspace_openapi_responses_are_explicitly_typed() -> None:
    openapi = _openapi()
    paths = openapi["paths"]

    expected = {
        ("/api/v1/workspace/session", "get"): "WorkspaceSessionResponse",
        (
            "/api/v1/workspace/organizations/{organization_id}",
            "get",
        ): "WorkspaceSnapshotResponse",
        (
            "/api/v1/workspace/organizations/{organization_id}/convergence",
            "get",
        ): "WorkspaceConvergenceResponse",
        (
            "/api/v1/workspace/organizations/{organization_id}/convergence",
            "patch",
        ): "WorkspaceConvergenceUpdateResponse",
        (
            "/api/v1/workspace/organizations/{organization_id}/chat",
            "post",
        ): "SatchyChatResponse",
        (
            "/api/v1/workspace/organizations/{organization_id}/actions/{action_id}",
            "post",
        ): "WorkspaceActionReviewResponse",
        (
            "/api/v1/workspace/organizations/{organization_id}/observations",
            "post",
        ): "WorkspaceObservationResponse",
    }

    for (path, method), schema_name in expected.items():
        response = paths[path][method]["responses"]["200"]["content"]["application/json"]["schema"]
        assert response["$ref"].endswith(f"/{schema_name}")


def test_checked_in_declarations_match_openapi_generator_exactly() -> None:
    openapi = _openapi()
    first = render_typescript_declarations(openapi)
    second = render_typescript_declarations(openapi)

    assert first == second
    assert SDK_DTS.read_text(encoding="utf-8") == first


def test_generated_declarations_cover_workspace_and_discovery_contracts() -> None:
    declarations = render_typescript_declarations(_openapi())

    required = {
        "export type WorkspaceSnapshotResponse =",
        "export type WorkspaceConvergenceResponse =",
        "export type WorkspaceDiscoveryState =",
        "export type SatchyChatResponse =",
        "export type SatchyRunResponse =",
        "export class TerraSatchClient",
        "connectEvents(options:",
    }
    for marker in required:
        assert marker in declarations

    snapshot = declarations.split("export type WorkspaceSnapshotResponse =", 1)[1].split(
        "\n\n", 1
    )[0]
    integrations = declarations.split(
        "export type WorkspaceIntegrationCatalogItem =", 1
    )[1].split("\n\n", 1)[0]
    assert "unknown" not in snapshot
    assert "runtime_ready" in integrations
    assert "capability_details" in integrations


def test_checked_in_sdk_runtime_keeps_existing_workspace_and_realtime_paths() -> None:
    runtime = SDK_JS.read_text(encoding="utf-8")
    declarations = SDK_DTS.read_text(encoding="utf-8")

    for path in (
        "/api/v1/workspace/session",
        "/api/v1/workspace/organizations/",
        "/ws/v1/events",
    ):
        assert path in runtime

    for method in (
        "workspaceSession()",
        "getWorkspace(organizationId)",
        "chatWithSatchy(organizationId, payload, csrfToken)",
        "getSatchyRun(organizationId, runId)",
        "reviewSatchyAction(",
        "connectEvents(",
    ):
        assert method in runtime or method in declarations

    assert "resolveUrl?: (path: string) => string;" in declarations
    assert 'RealtimeTopic = "events" | "transmissions" | "transcripts"' in declarations


def test_repository_exports_sdk_as_installable_package() -> None:
    package = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))

    assert package["name"] == "@terrasatch/sdk"
    assert package["type"] == "module"
    assert package["sideEffects"] is False
    assert package["exports"]["."]["types"] == "./sdk/typescript/index.d.ts"
    assert package["exports"]["."]["import"] == "./sdk/typescript/index.js"
