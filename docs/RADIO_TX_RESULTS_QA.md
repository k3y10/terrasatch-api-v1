# Radio transmitted results and Edge compatibility

This companion to terrasatch-edge PR #11 adds authenticated command capability discovery and
`transmitted` results. Existing ingestion and simulated/failed result contracts remain supported.
No schema migration is needed: outbound transmitted status/timestamps already exist.

The API rechecks RF policy at ACK, validates RF/action/outbound linkage before completing a
transmitted result, rejects simulation mislabeled as RF, and preserves immutable terminal
results. Already acknowledged attempts can report after expiry, so delayed delivery does not
lose evidence. Expiry still blocks starting new work. Command timestamps explicitly emit UTC.

## QA on 2026-09-08

- Current main `17ea63b4d0357484c56d541fee817a4aef5a7bbe`: 195 tests passed.
- Proposed code: 200 tests passed; full `scripts/qa-local.sh` passed (Ruff, imports, regression,
  coverage, migration graph, CLI/OpenAPI, deterministic fallback).
- Intelligence/STT contract coverage: 92.53%, minimum 80%.
- Command lifecycle coverage: 86.26%, minimum 80%, measured separately from intelligence.
- Edge: 194 tests passed, command/TX coverage 91.41% against a 90% minimum.
- Four real-route, authenticated API/Edge scenarios pass against current API source; four pass
  against this update. They cover ingestion/idempotency, approval and simulation, RF capability
  negotiation, foreign-device rejection, and result delivery recovery without a second TX.

Cross-repository reproduction lives in Edge `scripts/qa-api-compatibility.sh`: install both
repositories' dev dependencies and invoke with the API checkout plus `0` for current main or
`1` for this branch. The tests use SQLite ORM sessions and a fake radio provider; Redis event
publication is substituted. Production `/health` was read-only and healthy on the current-main
revision. No production commands or deployments were performed.

Deploy API support before enabling Edge RF. The generic external bridge adapter still needs
an installed hardware implementation and physical PTT/watchdog/RX-restoration acceptance.
These tests do not verify field STT accuracy, Windows native packaging or PostgreSQL concurrency.
