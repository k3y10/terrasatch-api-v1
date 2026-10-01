# @terrasatch/sdk

The canonical TypeScript client surface for TerraSatch.

- Runtime client: dependency-free ESM.
- Type declarations: generated from the FastAPI OpenAPI document.
- Browser sessions: supported through a custom `resolveUrl` transport (used by the Satchy workspace bridge).
- External applications: supported with `baseUrl` + bearer `token`.
- Realtime: supports the authenticated `/ws/v1/events` subscribe handshake.

Do not hand-edit `index.d.ts`. Regenerate it with:

```bash
uv run python scripts/generate-typescript-sdk.py
```

The repository QA suite verifies that the checked-in declarations exactly match the current OpenAPI document.
