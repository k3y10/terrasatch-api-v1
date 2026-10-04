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
satellites, weather, alerts, and human verification. Watch Duty's 2025 annual report also describes
AI-assisted image detection, official-document parsing, and a speech-to-text radio transcription
service in development, while retaining human-written alerts.

Sources:
https://technosylva.com/fire-agencies/
https://www.watchduty.org/how-it-works/overview
https://www.watchduty.org/blog/2025-annual-report

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

The current production platform still has these gaps. The isolated vNext branch addresses several
of them in code, but none should be considered production-complete until the promotion stages have
run against representative data and humans have reviewed the results.

### P0 — now implemented in the isolated vNext runtime

- source-classified `ContextPacket`
- auditable `AgentRun` contract
- provider-neutral model registry, routing, fallback, and local-only restricted-data routing
- claim-level evidence grounding
- typed tools with READ / PROPOSE_WRITE / EXTERNAL_WRITE / PHYSICAL effects
- explicit tool scopes and fail-closed policy decisions
- approval-gated action proposals
- context freshness and conservative contradiction checks
- model/tool latency and usage records
- AvyTS / PyroTS / HydroTS / GeoTS / InfraTS domain profiles
- deterministic eval and promotion gates
- semantic answer constraints
- cross-domain seed benchmark corpus
- local sandbox CLI and benchmark runner
- append-only local AgentRun trace store
- compatibility bridge from the current SatchyContext
- measured trial-impact metrics for time saved, acceptance, and reviewer edits

These are sandbox capabilities only. They do not alter current production routes or behavior.

### P0 — still required before any production canary

1. Run the vNext tests and benchmark corpus in a real Python environment and record the results.
2. Add read-only sandbox adapters for EchoSatch, GridSatch, CoreSatch, and QuakSatch.
3. Persist AgentRuns and reviewer feedback in a staging-grade audit store.
4. Build a much larger reviewed eval corpus from real field shorthand and organization workflows.
5. Measure unsupported-claim rate, claim-evidence precision/recall, and abstention behavior.
6. Run current Satchy and vNext side by side in shadow mode on the same authorized context.
7. Add an internal review UI with evidence drill-down, model route, tool calls, and feedback.
8. Complete threat modeling for prompt injection, cross-tenant access, secrets, retention, and egress.
9. Validate local-model performance and resource use on actual EdgeSatch hardware.
10. Require zero direct external-write/physical-execution paths in the agent runtime.

### P1 — context and field advantage

1. Consolidate GridSatch identity across API terrain cells, AvyTS H3 cells, and TerraSatch Map.
2. Add real DEM/terrain, environmental, temporal, and incident-history context behind GridSatch.
3. Finish repeated RF -> audio -> STT -> event field validation across supported radio targets.
4. Cache enough GridSatch/CoreSatch context for useful degraded/offline operation.
5. Add cross-source handoff, shift summarization, and contradiction-resolution workflows.
6. Treat callsigns, location aliases, field shorthand, and organization terminology as eval data.
7. Keep official, observed, modeled, derived, and AI-interpreted information visually distinct.

### P1 — customer impact

1. During the 14-day trial, show what Satchy listened to, structured, linked, summarized, and drafted.
2. Measure actual manual time versus Satchy-assisted time for repeated workflows.
3. Track approval acceptance, rejection reason, and reviewer edit ratio.
4. Make every important factual statement expandable to its evidence and provenance.
5. Learn organization terminology, SOPs, and report templates without turning habits into facts.
6. Do not claim monetary ROI unless the customer supplies an approved cost baseline.

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

- ContextPacket with source class, sensitivity, spatial/environmental/operational context
- AgentRun, claim-level grounding, model route, tool results, warnings, and usage records
- provider-neutral model registry/router with multiple model variants and fallback
- local Ollama and deterministic static providers
- restricted-context local-only model routing
- AvyTS, PyroTS, HydroTS, GeoTS, InfraTS, and general domain profiles
- typed tool registry with explicit scopes and side-effect classes
- fail-closed policy engine that separates hard blocks from human-review proposals
- approval-gated action proposals; no direct external or physical execution
- prompt-injection boundary language and malicious-transcript benchmark cases
- context freshness and conservative same-location contradiction detection
- memory interfaces that default to no writes
- in-memory and append-only local AgentRun trace stores
- deterministic eval scoring, semantic answer constraints, and promotion thresholds
- repeatable benchmark runner plus a cross-domain seed corpus
- measured trial-impact summaries using observed baselines only
- current-Satchy compatibility bridge
- explicit EchoSatch/GridSatch/CoreSatch/QuakSatch contracts
- local sandbox CLI that does not start the production API

It does **not** connect production handlers, migrate database tables, rename current production
modules, alter API routes, or enable Satchy vNext for customers.
