"""Deterministic TypeScript declaration generation from TerraSatch OpenAPI."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any

_IDENTIFIER = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$]*$")


def canonical_openapi_json(openapi: Mapping[str, Any]) -> str:
    return json.dumps(openapi, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def openapi_sha256(openapi: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_openapi_json(openapi).encode()).hexdigest()


def _schema_name(ref: str) -> str:
    return ref.rsplit("/", 1)[-1]


def _property_name(name: str) -> str:
    return name if _IDENTIFIER.fullmatch(name) else json.dumps(name)


def _literal(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    return json.dumps(value, ensure_ascii=False)


def _typescript_type(schema: Any, indent: int = 0) -> str:
    if not isinstance(schema, Mapping):
        return "unknown"

    ref = schema.get("$ref")
    if isinstance(ref, str):
        return _schema_name(ref)

    if "const" in schema:
        return _literal(schema["const"])

    enum = schema.get("enum")
    if isinstance(enum, list) and enum:
        return " | ".join(_literal(value) for value in enum)

    for union_key in ("anyOf", "oneOf"):
        variants = schema.get(union_key)
        if isinstance(variants, list) and variants:
            rendered = []
            for variant in variants:
                value = _typescript_type(variant, indent)
                if value not in rendered:
                    rendered.append(value)
            return " | ".join(rendered)

    all_of = schema.get("allOf")
    if isinstance(all_of, list) and all_of:
        return " & ".join(_typescript_type(item, indent) for item in all_of)

    raw_type = schema.get("type")
    if isinstance(raw_type, list):
        parts = []
        for item in raw_type:
            rendered = _typescript_type({**schema, "type": item}, indent)
            if rendered not in parts:
                parts.append(rendered)
        return " | ".join(parts)

    if raw_type == "null":
        return "null"
    if raw_type == "string":
        return "string"
    if raw_type in {"integer", "number"}:
        return "number"
    if raw_type == "boolean":
        return "boolean"
    if raw_type == "array":
        item_type = _typescript_type(schema.get("items", {}), indent)
        if " | " in item_type or " & " in item_type:
            return f"({item_type})[]"
        return f"{item_type}[]"

    properties = schema.get("properties")
    additional = schema.get("additionalProperties")
    if raw_type == "object" or isinstance(properties, Mapping) or additional is not None:
        if not properties:
            if isinstance(additional, Mapping):
                return f"Record<string, {_typescript_type(additional, indent)}>"
            return "Record<string, unknown>"

        required = set(schema.get("required") or [])
        pad = " " * indent
        child_pad = " " * (indent + 2)
        lines = ["{"]
        for name in sorted(properties):
            prop_schema = properties[name]
            optional = "" if name in required else "?"
            prop_type = _typescript_type(prop_schema, indent + 2)
            prop_lines = prop_type.splitlines()
            if len(prop_lines) == 1:
                lines.append(
                    f"{child_pad}{_property_name(name)}{optional}: {prop_lines[0]};"
                )
            else:
                lines.append(
                    f"{child_pad}{_property_name(name)}{optional}: {prop_lines[0]}"
                )
                lines.extend(f"{child_pad}{line}" for line in prop_lines[1:-1])
                lines.append(f"{child_pad}{prop_lines[-1]};")
        if additional is True:
            lines.append(f"{child_pad}[key: string]: unknown;")
        elif isinstance(additional, Mapping):
            lines.append(
                f"{child_pad}[key: string]: {_typescript_type(additional, indent + 2)};"
            )
        lines.append(f"{pad}}}")
        return "\n".join(lines)

    return "unknown"


def render_typescript_declarations(openapi: Mapping[str, Any]) -> str:
    schemas = (
        openapi.get("components", {}).get("schemas", {})
        if isinstance(openapi.get("components"), Mapping)
        else {}
    )
    digest = openapi_sha256(openapi)
    lines = [
        "// AUTO-GENERATED FROM TERRASATCH OPENAPI. DO NOT EDIT BY HAND.",
        f"// openapi-sha256: {digest}",
        "",
    ]

    for name in sorted(schemas):
        lines.append(f"export type {name} = {_typescript_type(schemas[name])};")
        lines.append("")

    lines.extend(
        [
            'export type RealtimeTopic = "events" | "transmissions" | "transcripts";',
            "",
            "export type TerraSatchClientOptions = {",
            "  baseUrl?: string;",
            "  wsBaseUrl?: string;",
            "  token?: string;",
            '  credentials?: RequestCredentials;',
            "  fetch?: typeof fetch;",
            "  resolveUrl?: (path: string) => string;",
            "  WebSocket?: typeof WebSocket;",
            "};",
            "",
            "export type TerraSatchRequestOptions = RequestInit & {",
            "  csrfToken?: string;",
            "};",
            "",
            "export class TerraSatchApiError extends Error {",
            "  status: number;",
            "  detail: unknown;",
            "  constructor(status: number, message: string, detail?: unknown);",
            "}",
            "",
            "export class TerraSatchClient {",
            "  constructor(options?: TerraSatchClientOptions);",
            "  request<T>(path: string, init?: TerraSatchRequestOptions): Promise<T>;",
            "  workspaceSession(): Promise<WorkspaceSessionResponse>;",
            "  loginWorkspace(",
            "    email: string, password: string, csrfToken: string",
            "  ): Promise<WorkspaceLoginResponse>;",
            "  logoutWorkspace(csrfToken: string): Promise<WorkspaceLogoutResponse>;",
            "  getWorkspace(organizationId: string): Promise<WorkspaceSnapshotResponse>;",
            "  getWorkspaceConvergence(",
            "    organizationId: string",
            "  ): Promise<WorkspaceConvergenceResponse>;",
            "  updateWorkspaceConvergence(",
            "    organizationId: string,",
            "    payload: WorkspaceConvergenceUpdate,",
            "    csrfToken: string,",
            "  ): Promise<WorkspaceConvergenceUpdateResponse>;",
            "  chatWithSatchy(",
            "    organizationId: string,",
            "    payload: Chat,",
            "    csrfToken: string,",
            "  ): Promise<SatchyChatResponse>;",
            "  listSatchyRuns(",
            "    organizationId: string, limit?: number",
            "  ): Promise<SatchyRunResponse[]>;",
            "  getSatchyRun(organizationId: string, runId: string): Promise<SatchyRunResponse>;",
            "  reviewSatchyAction(",
            "    organizationId: string,",
            "    actionId: string,",
            '    decision: "approve" | "reject",',
            "    csrfToken: string,",
            "    notes?: string,",
            "  ): Promise<WorkspaceActionReviewResponse>;",
            "  createWorkspaceObservation(",
            "    organizationId: string,",
            "    payload: Observation,",
            "    csrfToken: string,",
            "  ): Promise<WorkspaceObservationResponse>;",
            "  connectEvents(options: {",
            "    token?: string;",
            "    topics?: RealtimeTopic[];",
            "  }): WebSocket;",
            "}",
            "",
        ]
    )
    return "\n".join(lines)
