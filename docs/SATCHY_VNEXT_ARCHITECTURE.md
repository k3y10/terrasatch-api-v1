# Satchy vNext — isolated agent architecture

Status: **sandbox-only / not wired to production**

Branch: `feat/satchy-vnext-isolated-runtime`

## Why this exists

The current TerraSatch API already has useful Satchy capabilities: tenant-safe context, deterministic
radio intent handling, local Ollama support, source-linked operational events, action proposals,
human approval, field assets, and workspace assistance. The next step is not to replace those
working paths. It is to build and evaluate a dedicated agent harness beside them.

No production route imports `terrasatch.satchy_vnext`. The package defaults to disabled and its
runtime executes read-only tools only. External writes and physical commands are always emitted as
approval-gated proposals for the existing TerraSatch action control plane.

## TerraSatch technology boundaries

```text
EchoSatch  -> Signal       -> radio, voice, messages, field communications
EdgeSatch  -> Field runtime-> local capture, STT, offline queue, device capabilities
GridSatch  -> Context      -> terrain, location, environmental/spatial relationships
CoreSatch  -> Intelligence -> extraction, normalization, derivation, fusion
QuakSatch  -> Trust        -> identity, protected context, access and policy
Satchy     -> Action       -> reason, explain, orchestrate, propose
```

The current production names are not renamed by this branch. vNext uses these as future interface
boundaries so migration can happen incrementally.

## Runtime

```text
authorized ContextPacket
        |
        v
domain + risk classification
        |
        v
model router (local-first / connectivity aware)
        |
        v
structured AgentPlan
        |
        +--> evidence ID validation
        |
        +--> read-only tools ----------+
        |                              |
        |                         tool evidence
        |                              |
        +<--------- optional refinement+
        |
        +--> proposed writes / external / physical actions
        |              |
        |              v
        |       existing approval plane
        |
        v
auditable AgentRun
```

## ContextPacket

A model does not receive arbitrary database state. It receives a bounded ContextPacket containing:
organization/site/user scope, domain, connectivity, evidence, spatial context, environmental
context, operational context, user preferences, and policy context.

Evidence carries an explicit class:

- OBSERVED
- OFFICIAL_PUBLISHED
- MODELED
- DERIVED
- USER_PROVIDED
- AI_INTERPRETED

This distinction is foundational. Satchy must never silently turn a model estimate or its own prior
interpretation into a field observation.

## AgentRun

Every run records the request, selected domain, model route, model usage, grounded plan, tool
results, proposed actions, warnings, failures, and timestamps. The in-memory trace store is only a
sandbox adapter; staging should persist the same contract in a dedicated audit store.

## Models

vNext is provider-neutral. The included adapters are:

- `StaticModelProvider` for deterministic tests
- `OllamaModelProvider` for local structured inference

Cloud providers should be added as adapters, not hard-coded into Satchy. Routing is local-first and
connectivity-aware so EdgeSatch can support a degraded/offline mode later.

## Tools

Tools declare their effect:

- `READ`
- `PROPOSE_WRITE`
- `EXTERNAL_WRITE`
- `PHYSICAL`

Only READ tools can execute inside this runtime. All other effects become ProposedAction records.
Even ACTIVE mode does not bypass the existing approval/execution control plane.

Initial interface contracts:

- `echo.search_signals`
- `grid.resolve_context`
- `core.explain_derivation`
- `quak.authorize`
- `workspace.generate_report`
- `notify.team`
- `edge.command`

Handlers are intentionally not connected to production in this branch.

## Domain profiles

Satchy has shared orchestration with domain-specific vocabulary and safety rules:

- AvyTS
- PyroTS
- HydroTS
- GeoTS
- InfraTS
- General operations

Domain profiles should shape extraction and reasoning without creating five independent AI stacks.

## Security model

1. Context is tenant/site scoped before the model sees it.
2. Evidence and tool output are untrusted data, never instructions.
3. Factual operational claims must cite authorized evidence IDs.
4. Unknown evidence IDs are removed and lower confidence.
5. The model cannot grant itself access or lower tool risk.
6. Side effects are proposals.
7. QuakSatch is the future trust/access interface; the existing approval plane remains authoritative.
8. No Satchy-generated text is a substitute for official forecasts, incident command, or qualified
   human judgment.

## Recommended next integration order

1. Keep this package isolated and grow the eval corpus.
2. Add read-only adapters against fixture/sandbox data for EchoSatch and GridSatch.
3. Add CoreSatch derivation lineage as read-only evidence.
4. Add QuakSatch authorization checks once that contract is finalized.
5. Run shadow evaluations beside current Satchy without showing users vNext output.
6. Compare current vs vNext on grounding, latency, cost, and human preference.
7. Canary read-only workspace answers for internal users.
8. Only after promotion gates pass, allow vNext to create proposals in the existing action plane.
9. Never grant direct physical or external-write authority to the model runtime.
