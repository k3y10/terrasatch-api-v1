# Satchy vNext — competitive and gap analysis

Research date: 2026-09-27

This document is product/engineering research, not an assertion that any competitor has identical
scope to TerraSatch.

## What the market is converging on

### Mission-critical AI remains human-led

Motorola Solutions Assist positions AI across command-center and field workflows while keeping
personnel in control of consequential decisions. It can prepare incidents from transcribed radio
traffic pending dispatcher confirmation and works across mission-critical communications.

Source:
https://www.motorolasolutions.com/en_us/ai/assist.html

Axon Draft One generates report drafts from body-camera transcripts but requires officer review and
approval. Axon also emphasizes audit history and evidence-side review.

Sources:
https://www.axon.com/responsibility/draft-one
https://www.axon.com/products/draft-one

**TerraSatch implication:** existing approval gates are an advantage. Do not trade them away for
agent autonomy. Improve provenance, review UX, and measurable time savings.

### Operational agents need durable, inspectable workflows

Palantir's operational application guidance keeps humans accountable at critical decision points
while agents handle bounded routine work, with decisions and rationale retained as durable data.

Source:
https://www.palantir.com/docs/foundry/app-building/operational-apps

LangGraph emphasizes human-in-the-loop, persistence, and controlled graph workflows. Temporal's AI
guidance emphasizes durable execution across crashes, timeouts, and waits for human approval.

Sources:
https://www.langchain.com/langgraph
https://docs.temporal.io/ai

**TerraSatch implication:** Satchy needs a first-class AgentRun/audit model and durable workflow
adapter before it becomes responsible for long-running operations.

### Geospatial products are getting deeper, not thinner

Esri continues expanding task-specific and foundation GeoAI models inside ArcGIS. onX Backcountry
combines high-resolution terrain data, offline maps, slope/aspect, avalanche forecasts, SNOTEL and
terrain analysis. TAK remains a strong shared-situational-awareness and plugin platform.

Sources:
https://www.esri.com/arcgis-blog/products/arcgis/geoai/whats-new-in-ai-tools-and-models-in-arcgis-q2-2026
https://www.onxmaps.com/backcountry/app/features
https://tak.gov/products

**TerraSatch implication:** GridSatch cannot be a cosmetic map layer. It needs canonical spatial IDs,
real DEM/terrain data, source lineage, offline context, and domain overlays that can be cited by
Satchy.

### Domain platforms transform raw data into operational workflows

Tomorrow.io now exposes conversational weather intelligence, MCP tools/data feeds, persistent event
identity, operational dashboards, protocols, and operation logs.

Sources:
https://www.tomorrow.io/blog/the-july-2026-release/
https://www.tomorrow.io/weather-intelligence-platform/
https://support.tomorrow.io/hc/en-us/articles/39329004302484-Logging-Weather-Driven-Operational-Decisions-in-the-Operations-Log

Technosylva combines wildfire simulations, situational awareness, field observations, incident
mapping and resource context. Watch Duty combines official sources, radio monitoring, maps,
satellites, weather, alerts, and human verification.

Sources:
https://technosylva.com/fire-agencies/
https://www.watchduty.org/how-it-works/overview

**TerraSatch implication:** the differentiator is not another dashboard. It is the cross-source
field pipeline: EchoSatch + EdgeSatch + GridSatch + CoreSatch + Satchy, with provenance preserved.

## Current TerraSatch strengths

Based on the current repositories:

- Canonical Transmission -> Transcript -> intelligence -> OperationalEvent path
- Deterministic extraction with a local Ollama provider option
- Tenant/site scoped Satchy context
- Source-linked operational evidence
- Conservative deterministic radio intents
- Approval-gated actions and mission controls
- Edge device identity/capability policies
- Local Faster Whisper and continuous RX work in EdgeSatch
- Terrain-cell/master-data foundations and separate AvyTS/H3 prototypes
- Workspace integrations that remain proposal/approval oriented

These are unusually relevant building blocks for field AI.

## Gaps that matter before production Satchy

### P0 — trust and evaluation

1. No canonical AgentRun contract persisted across all Satchy interactions.
2. No broad domain eval corpus with known expected evidence, tool, and safety outcomes.
3. No measured hallucination/unsupported-claim rate.
4. No calibrated confidence or abstention benchmark.
5. No explicit shadow/canary promotion gates.
6. No standardized contradiction handling across radio, official data, sensors, and models.

### P0 — context

1. Current SatchyContext is useful but not yet a source-classified ContextPacket.
2. GridSatch concepts are spread across API master data, TerraSatch Map, and AvyTS.
3. No single context retrieval contract for spatial/environmental/incident history.
4. Limited long-running incident/shift context.
5. User adaptation exists, but operational facts must remain separate from preferences.

### P0 — agent runtime

1. Current Satchy model use is tied closely to the API provider setting.
2. No model capability router/fallback chain across local/remote model classes.
3. No general typed tool registry.
4. No side-effect taxonomy shared across all tools.
5. No durable agent workflow state for multi-minute/hour tasks.
6. No per-run latency/token/cost/quality telemetry.

### P1 — field advantage

1. Finish and repeatedly field-test RF -> audio -> STT -> event ingestion.
2. Add degraded/offline Satchy with local model and cached GridSatch context.
3. Treat radio shorthand, callsigns, location aliases and domain vocabulary as first-class eval data.
4. Add cross-source contradiction detection and handoff/shift summarization.
5. Make evidence review one click from every Satchy factual statement.

### P1 — customer value

1. Measure minutes of work avoided per report/handoff/observation.
2. During the 14-day trial, show what Satchy listened to, structured, linked, summarized and drafted.
3. Show approval acceptance/edit rate rather than generic "AI usage."
4. Build reusable organization terminology, SOP and reporting templates.
5. Make "why Satchy said this" visible, not hidden behind a confidence number.

## Defensible TerraSatch position

Do not compete as a general chatbot, generic map, generic weather model, or generic incident system.

The defensible product loop is:

```text
FIELD SIGNAL
    -> EchoSatch / EdgeSatch
    -> preserved source + transcript

WHERE / CONDITIONS
    -> GridSatch
    -> terrain + environmental + temporal context

STRUCTURE / FUSION
    -> CoreSatch
    -> normalized, derived, source-linked intelligence

TRUST
    -> QuakSatch + existing policy/approval plane
    -> identity, access, provenance, approval

REASON / WORK
    -> Satchy
    -> answer, draft, explain, propose, handoff

DOMAIN
    -> AvyTS / PyroTS / HydroTS / GeoTS / InfraTS
```

The product advantage is that a radio call or field observation can become a source-linked,
spatially grounded operational record and useful work without losing the original evidence.

## What vNext implements now

The isolated `terrasatch.satchy_vnext` package adds:

- ContextPacket and evidence classes
- AgentRun and model usage records
- provider-neutral model registry/router
- local Ollama and deterministic static providers
- model fallback
- domain profiles
- typed tool registry
- effect/risk classification
- fail-closed policy engine
- approval-gated action proposals
- prompt-injection boundary language
- memory interfaces that default to no writes
- trace store interface
- deterministic eval scoring and promotion thresholds
- explicit EchoSatch/GridSatch/CoreSatch/QuakSatch contracts

It does **not** connect production handlers, migrate database tables, rename current production
modules, alter API routes, or enable Satchy vNext for customers.
