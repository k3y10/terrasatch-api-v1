# Natural radio addressing and Satchy field workflows

Branch: `feat/natural-radio-addressing`, based on current `main`.

## Architecture

Radio addressing remains deterministic in `radio/addressing.py`. TerraEngine still extracts and persists events independently before control-plane evaluation. The new `actions/field_intent.py` classifies explicit commands and stages bounded context; it does not call an LLM, insert observations, generate final reports, notify anyone, or execute radio transmission. Existing policy filtering, human approval, emergency review, and outbound simulation remain intact.

No new database models, action types, schema changes, or migrations are required. The existing conversation model remains intact, including legacy unaddressed conversation annotation after event persistence. Lack of an explicit recipient does not suppress extraction or create a reply.

## Changed files

- `src/terrasatch/radio/addressing.py`: configured-label parser, ambiguity handling, message body and pattern audit output.
- `src/terrasatch/radio/conversations.py`: agent-name lookup also checks site/enabled status; prevents future activity from matching an older transmission.
- `src/terrasatch/actions/field_intent.py`: deterministic workflow rules, location ambiguity checks, safe source/reference staging, scoped report snapshots.
- `src/terrasatch/actions/evaluation.py`: evaluates message-body intent after addressing, preserves emergency precedence and policy gates, persists audit context and structured proposals.
- `tests/unit/test_natural_radio.py`: parser, alias, conversation, isolation, timeout, standalone capture tests.
- `tests/unit/test_field_intent.py`: command classification, passive capture, idempotent evaluation, policy suppression, emergency precedence, scoped report context, location clarification and unique incident targeting.
- `docs/natural-radio-workflows.md`: this review and behavior contract.

## Addressing

Precedence: `X to Y`, `X calling Y`, `Y, this is X`, `Y from X`, `X for Y`, recipient-first `Y, X`, recipient-only, callsign hint, unresolved.

Names resolve through enabled callsigns in the organization and current site (or organization-wide callsigns). Matching is case-insensitive, whitespace-normalized, alias-aware, and longest-first. Satchy aliases such as TerraSatch inherit agent addressing through the configured callsign. Colliding callsign aliases remain unresolved instead of selecting a row arbitrarily. Base and Field are not hardcoded.

Resolved direction does not alter the participant fingerprint. Reversed Base/Field traffic reuses the same open conversation when organization, site, channel, participants and timeout match. The default remains 300 seconds. A transmission cannot reuse a conversation whose last activity is later than its receive timestamp.

## Workflow proposals

Emergency detection retains precedence regardless of addressing. Otherwise workflow evaluation requires explicit Satchy addressing.

| Message body | Proposal |
| --- | --- |
| log this/that/an observation; record this; note that/for | create_observation |
| add this/that to the current incident/event; update the event | update_event |
| notify Base about ... | notify_team |
| prepare/generate/draft my report/handoff; summarize my observations | generate_report |
| bare call; how copy; radio check; question | reply_radio |
| incomplete recognized command; ambiguous configured location; report without resolved operator | ask_clarification |
| passive observations, weather, snowpit statements | no action |

Rules operate at the beginning of the parsed message body, with optional `please`. Quoted or narrated commands and ordinary non-addressed observations do not become workflows. Compound commands are not decomposed into multiple actions.

All proposals retain organization, site, source transmission, conversation, source event, operator and channel context where available. All remain subject to allowed action types, suggest mode and approval. Non-radio workflows are staging proposals: the existing outbound queue accepts only reply_radio. No workflow executor is added.

Observation proposals reference substantive events already extracted using `associate_or_enrich`; bare references use `stage_reference` and require source selection. They never insert a duplicate observation. The source event is the record of the current transmission, not automatically the antecedent of “that”.

Event updates distinguish their source event from `target_event_id`. A target is proposed only when exactly one earlier INCIDENT/MEDICAL/AVALANCHE/FIRE event exists in the same scoped conversation. Otherwise `requires_target_selection` is true; no cross-conversation or global latest-event inference occurs.

Notification recipient text is staged for confirmation, not resolved to an external destination or transmitted.

Location clarification uses the existing effective organization/site operational profile. Supported `location_aliases` forms are canonical name to alias list, or alias to canonical name string. Exact matches take precedence; shared aliases or partial prefixes matching multiple locations require clarification. This is not a replacement for TerraEngine spatial grounding.

## Field memory and reports

Existing records suffice for a proposal containing an identified operator's transmissions and linked events across conversations/channels at one site. The operator must resolve to a configured callsign ID (an alias-aware callsign hint also resolves to that ID). A receiver identity is never substituted for a field operator.

Reports contain source transmission IDs, event IDs, conversation IDs, report kind, organization/site/operator context, and explicit time bounds. The current default is UTC midnight through the request's API receive time, marked `requires_time_window_confirmation`. There is no configured site timezone/shift model, so this window is not represented as an exact local shift. Selection is capped at 500 transmissions with a visible truncation flag. Reports are source snapshots for a draft workflow, not generated prose or outbound reports.

Unidentified passive traffic remains stored, but cannot safely appear in an operator-specific report without later attribution. Previous records with unresolved speaker IDs need attribution/backfill before inclusion. Delayed uploads are scoped by API `received_at`, not field capture time; custom date ranges, local timezones, shifts crossing midnight, and final report generation remain follow-up work.

## Limits and unsupported phrasing

- Address pairs must appear at the start of the transmission and end at punctuation or end of text. Unpunctuated `Field to Base radio check` remains unresolved.
- Unknown callsigns, STT spelling errors, multiple recipients, mid-message addressing, and overlapping aliases require review/configuration; arbitrary prose is not treated as a callsign.
- Unpunctuated single-name calls such as `Satchy emergency` may remain unaddressed; emergency review still detects emergency terms independently.
- `Field observation ...` alone does not establish which configured operator spoke; use an explicit address pair or reliable per-transmission callsign hint when known.
- Bare “that” does not infer an observation from unrelated conversations. A unique prior incident is a review candidate, not an automatically executed update.
- Location matching is limited to the supported profile alias forms and an at/near phrase. Broader gazetteer/fuzzy resolution is not added.
- Existing deterministic extraction vocabulary and emergency term matching remain unchanged; this change does not claim new clinical or hazard inference accuracy.

## Validation

- Full suite: 257 passed (including 62 new cases).
- Repository-wide Ruff lint: passed.
- Formatting of all six changed Python files: passed.
- Repository-wide formatting: existing baseline fails; a clean archive of `main` reports 45 files requiring formatting with the installed Ruff. Those unrelated files were not changed.
- Alembic: single existing head `0010_satchy_action_control_plane`; PostgreSQL upgrade SQL generation through head passed. No live PostgreSQL migration was applied.
- No schema/model/migration files changed. No deployment or merge performed.

## Separate terrasatch-edge follow-up

Map physical FRS/BCA channels to API channel_id. Propagate richer RF provenance including receiver identity, frequency, channel and privacy metadata. Improve continuous monitoring and avoid a static callsign when one SDR hears multiple operators. Edge remains responsible for RF reception, bounded audio, local STT and transport; business semantics and workflow policy remain in the API. Physical TX/PTT is outside this work.
