# Unified workspace capacity notes

This is a deployment budget, not a measured capacity claim. The workspace and email use
one API process, the existing account session, and the existing PostgreSQL service. Do not
deploy the separate internal-inbox service alongside this integrated mailbox implementation.

## Existing staging limits

| Container | Memory cap | CPU cap |
| --- | ---: | ---: |
| API | 384 MiB | 0.15 |
| Worker | 384 MiB | 0.05 |
| PostgreSQL | 384 MiB | 0.10 |
| Redis | 128 MiB | 0.05 |
| Ollama | 2304 MiB | 0.50 |
| Total | 3584 MiB (3.5 GiB) | 0.85 |

On the reported 1 OCPU / 6 GiB Oracle host this leaves nominal room for the OS, proxy,
Docker and other workloads. Caps are ceilings, not reservations or proof that concurrent
production and staging workloads fit. Inventory all running containers before deployment.
Do not increase API worker count: each process adds a database pool and resident memory.

Docker logs now rotate at 10 MB with three files per container (approximately 150 MB for
these five containers). This bounds container log growth, not database, model, or Redis
volume growth. Existing containers need recreation for this logging setting to take effect.

## Current application bounds and remaining work

- The shared session factory caches one engine per database URL in each process, with
  five pooled connections and up to five overflow connections. API and worker together
  can therefore use up to twenty application connections, plus probes and maintenance.
- Readiness probes create and dispose a separate engine and check Redis with two-second
  timeouts. Keep readiness polling at the infrastructure level; workspace views should
  not create a new readiness probe for every panel refresh.
- Email lists return 100 messages by default, capped at 200. The list selects summary fields, the first 1024 text characters and an attachment
  count in SQL. It does not load full text/HTML bodies or attachment metadata into the
  application. Preview whitespace is normalized and the visible preview capped at 220
  characters; detailed messages remain available on demand.
- There is no cursor pagination for older mail and no automatic retention policy. Add
  pagination and an explicit retention/backup policy before treating this as a large mailbox.
- Workspace mail is restricted to internal TerraSatch users and explicit mailbox grants.
  Customer organization membership must not imply access to staff email.
- Email provider calls have ten-second timeouts. Sending must retain existing authorization,
  CSRF and idempotency controls; an embedded UI must not bypass those API checks.
- The existing billing worker checks its outbox every fifteen seconds. Do not start an
  extra worker or a browser polling loop for each opened workspace section.
- Ollama already limits concurrent inference to one request and one loaded model. It has
  a 2.25 GiB memory ceiling. Measure queueing and API responsiveness during inference
  before increasing users or model size; keep inference off the web-request critical path
  wherever the current workflow supports it.
- Redis has a 64 MB data limit with no eviction. At the limit, writes fail rather than
  deleting keys. Alert on rejected writes and memory pressure; do not silently switch
  eviction policies for data used by sessions, rate limits, or queues.

## Deployment verification

Before rollout record host available memory, swap activity, disk usage, container memory/CPU
and PostgreSQL connections under both idle and representative active use. Exercise sign-in,
organization switching, mailbox access, a provider failure and an Edge heartbeat while an
inference request is active. Verify workspace navigation does not reload all modules or
poll hidden panels. Do not label the service healthy from a successful static page alone.

No live host measurements or deployment were performed for this capacity note.
