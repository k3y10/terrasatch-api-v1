# Satchy Discovery Evidence

Discovery evidence is the append-only record behind TerraSatch's 14-day **LISTEN · WATCH · LEARN · ADAPT** experience.

This layer records what TerraSatch actually observed, identified, tested, approved, or rejected. It does not infer savings, operational truth, or workflow success without evidence.

## Event types

- `signal_observed` — an authorized input was observed.
- `context_observed` — authorized workspace or operational context was observed.
- `workflow_identified` — a repeatable workflow candidate was identified.
- `workflow_testing` — a workflow candidate entered controlled testing.
- `workflow_approved` — an authorized human approved the workflow.
- `workflow_rejected` — an authorized human rejected the workflow.

Workflow events require a stable `workflow_key`.

## Evidence and idempotency

Events are append-only through the workspace API. Each event can carry:

- organization and optional site
- actor user when a human certified the event
- source type and source reference
- stable workflow key and display label
- bounded confidence
- structured evidence
- optional dedupe key
- occurred and created timestamps

`organization_id + dedupe_key` is unique. Retrying the same evidence with the same dedupe key returns the existing event instead of inflating Discovery counts.

## Derived workflow counts

Counts are derived from the latest evidence state for each unique workflow key:

- **Identified** — every unique workflow ever identified or moved to a later state.
- **Testing** — workflows whose latest state is `workflow_testing`.
- **Approved** — workflows whose latest state is `workflow_approved`.
- **Rejected** — workflows whose latest state is `workflow_rejected`.

A workflow moving from testing to approved therefore reduces Testing by one and increases Approved by one. Repeated events do not count as additional workflows.

## Phase evidence

The summary also reports whether evidence exists for each Satchy phase:

- LISTEN: at least one `signal_observed`
- WATCH: at least one `context_observed`
- LEARN: at least one unique workflow
- ADAPT: at least one workflow currently testing or approved

These evidence flags do **not** grant runtime permissions or authorize consequential actions.

## Workspace API

Authenticated members may read:

- `GET /api/v1/workspace/organizations/{organization_id}/discovery`
- `GET /api/v1/workspace/organizations/{organization_id}/discovery/events`

Admin/owner users may append manually certified evidence with CSRF protection:

- `POST /api/v1/workspace/organizations/{organization_id}/discovery/events`

Automatic Satchy/system capture should call the internal Discovery service directly and preserve the true source type/reference. It should never masquerade system evidence as a manual human event.

## Rollout boundary

This foundation intentionally does not:

- auto-detect workflow patterns yet
- alter the existing Discovery lifecycle JSON
- change Satchy runtime modes
- auto-approve adaptations
- calculate ROI without measured evidence
- change UAC, Snowbird, Edge, radio, or integration behavior

The next phase can safely connect canonical signals to this evidence layer and then surface evidence-derived counts in the workspace UI.
