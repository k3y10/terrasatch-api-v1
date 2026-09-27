# Satchy vNext promotion plan

Satchy vNext must earn production access. Time spent running in a sandbox is not a substitute for
measured quality.

## Stage 0 — isolated

- Package has no production import path.
- Static/local models only.
- Fixture/synthetic context.
- No network side effects.
- Unit and adversarial tests.

Exit criteria:

- 100% side-effect safety tests
- no unknown evidence IDs survive grounding
- deterministic fallback behavior
- all domain fixtures parse and run

## Stage 1 — shadow

Run vNext beside the current path on copied/authorized context. Do not display vNext output to the
customer and do not create production actions.

Measure:

- unsupported factual claim rate
- evidence citation precision/recall
- intent/domain accuracy
- tool-selection precision/recall
- action approval recall
- latency p50/p95
- local model success/fallback rate
- estimated cost per run
- disagreement with current deterministic extraction
- human reviewer preference on representative cases
- context contradiction/freshness detection
- measured manual time vs Satchy-assisted time
- proposal acceptance and reviewer edit ratio

Initial promotion thresholds:

- action safety: 100%
- grounding: >= 98%
- composite deterministic eval: >= 95%
- tool selection: >= 90%
- zero cross-tenant/context-policy violations
- zero direct write/physical execution paths

## Stage 2 — internal sandbox UI

Allow TerraSatch operators to compare current Satchy and vNext side by side.

Required UX:

- evidence/source drawer
- model/provider disclosure
- confidence + missing context
- tool calls
- proposed actions
- reason an action requires approval
- feedback: correct / wrong / incomplete / unsafe
- reviewer edits captured separately from source truth

## Stage 3 — canary read-only

Small internal/partner allowlist. Read-only answers, summaries, extraction and explanations only.

Rollback conditions:

- any tenant isolation failure
- any unsupported high-consequence factual claim
- any false claim that an action executed
- material latency regression
- degradation in grounding/eval metrics

## Stage 4 — proposal canary

vNext may create proposals in the existing Satchy action plane. It still cannot execute external or
physical effects.

Track:

- proposal acceptance rate
- edit distance before approval
- rejection reason
- time saved
- false positive action rate
- missing-context rate
- measured minutes saved per workflow
- reviewer edit ratio
- source records processed per accepted output

## Stage 5 — production decision support

Production Satchy may answer, summarize, draft and propose according to organization policy. Existing
approval controls remain authoritative.

Do not promote direct autonomous radio transmission, physical missions, public alerts, evacuation
orders, or other high-consequence external effects merely because model quality improves. Those
require their own policy, legal, operational, and field validation.

## Eval corpus to build next

At minimum, create versioned fixtures for:

### AvyTS
- natural vs human-triggered avalanche
- negative observations
- aspect/elevation shorthand
- D-size / R-size
- snowpit results
- location aliases
- forecast vs field observation conflicts

### PyroTS
- smoke vs confirmed fire
- perimeter/status updates
- red flag warnings
- evacuation information
- wind/spread ambiguity
- official vs radio conflict

### HydroTS
- gauge observation vs forecast
- flood watch/warning semantics
- rising/falling trends
- SWE/runoff relationships

### GeoTS
- rockfall/landslide observations
- uncertain location
- measured movement vs interpretation

### InfraTS
- stale telemetry
- repeater/communications status
- road/access changes
- asset command requests

### Cross-domain
- prompt injection inside transcripts/documents
- malicious tool arguments
- missing source IDs
- contradictory sources
- stale data
- offline mode
- model timeout/fallback
- cross-tenant IDs
- approval/rejection/cancel phrases


## Trial impact measurement

The 14-day Satchy trial should report observed value without inventing ROI.

For workflows such as field reports, handoffs, observation structuring, incident summaries, and
routine notifications, capture a reviewed baseline and the actual assisted completion time.

Report:

- measured minutes saved
- proposal/output acceptance rate
- reviewer edit ratio
- source records processed
- workflow count by type

Do not convert these measurements into a monetary ROI claim unless the customer supplies an
approved labor-cost or operational-cost baseline.
