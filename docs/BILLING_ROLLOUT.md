# TerraSatch subscription rollout — preview only

Do not merge, promote, enable live billing, or modify Stripe under the current pricing request.

## Catalog

`src/terrasatch/billing/plans.py` exposes `/api/v1/billing/plans`. Keep it aligned with the website's `src/lib/plan-catalog.ts`; the website retains pricing when the API is unavailable.

| Plan | Public monthly price | Checkout | Planned lookup key |
| --- | --- | --- | --- |
| Individual | $24 | 30-day card-required trial, when enabled | `terrasatch_individual_monthly_v2` |
| Team | $399 | 30-day card-required trial, when enabled | `terrasatch_team_monthly_v2` |
| Operations | From $1,999 | Sales/scoped only | None |
| Enterprise | Custom | Sales/scoped only | None |

Annual values are null. Optional annual discounts remain proposals. Old pitch-model prices are internal financial assumptions, not public minimums. The v2 keys deliberately differ from the already-created $49/$500 v1 sandbox prices; do not reuse or transfer the old lookup keys. Do not automatically migrate existing subscriptions.

## Gates and deployment order

1. Keep billing disabled and live mode false. Keep both PRs draft.
2. Build from the billing branch in an isolated staging directory/database; never migrate production for a preview. Apply migrations through 0015 and run API and worker from the same version.
3. Configure a protected Preview origin and staging-only server credentials. Identify the public staging webhook origin before creating endpoints. No default production URL is acceptable for a sandbox acceptance run.
4. After explicit renewed Stripe authorization, verify account `acct_1Txb0QPwzxCRGRdh`, test mode, and create the matching v2 catalog. Configure customer portal cancellation/payment methods; plan switching needs separate backend validation.
5. Production Stripe still requires a server-side restricted key and matching webhook signing secret. Billing email readiness accepts either direct Oracle-to-Resend credentials or the protected Vercel fallback, plus the activation signing secret. Never print credentials or commit environment files.
6. Verify the separate TerraSatch Resend sending domain. Preferred delivery is Oracle worker -> Resend using owner-only `TERRASATCH_RESEND_API_KEY`, `TERRASATCH_BILLING_FROM`, and optional `TERRASATCH_BILLING_REPLY_TO`. The protected Vercel `/api/billing-email` endpoint remains fallback-only and uses its own shared secret.
7. Exercise Individual and Team signup → Checkout → signed webhook → committed subscription/outbox → inbox activation → workspace login → customer portal. Card required, $0 today, billing after 30 days unless canceled. Operations/Enterprise must reject checkout.
8. Test duplicate/concurrent/out-of-order webhooks, payment failures, cancellation, DB rollback, email retries, expired/consumed activation links, tenant isolation and CORS. Provider/message-ID receipt tracking is implemented; add password-reset/resend plus Resend delivery/bounce webhook reconciliation before public release.
9. Confirm unit economics, retention semantics, support/hardware scope, tax registration/collection, subscription migration, and release base before requesting any production rollout.

Webhook event set: checkout.session.completed; customer.subscription.created/updated/deleted/trial_will_end; invoice.paid; invoice.payment_failed. Fresh subscription state and stale invoice ordering still need review. Live gate must remain false.

## Implemented safeguards and limits

Source/card data stays in its owning system: Stripe owns payment methods; TerraSatch owns tenant state and authorization. Browser inputs cannot select arbitrary Price IDs. Lookup key, amount, currency, cadence and subscription quantity are validated. Pending valid checkout is reused; near-expiry refresh remains an explicit retry conflict.

Email intents commit with billing state. The worker prefers direct Resend delivery and uses the protected Vercel sender only as a fallback. Retries reconstruct the same activation token and reuse the same provider idempotency key. Successful delivery records the provider and provider message ID in `billing_email_outbox`. Expired and consumed activations are held with `activation_expired` or `activation_consumed`; a token/signing-secret mismatch requires reconciliation. These terminal rows are not falsely marked sent and are not retried automatically. `billing email-status` exposes safe outbox state in the admin console without recipient/context data. Provider acceptance is not proof of inbox delivery; Resend delivery/bounce webhooks, operator resend and password reset remain open.

Sites, memberships, devices and channels have managed-plan checks. Processing-hour/retention allowances are not metered or pruned automatically. No new Satchy Agent or drone add-on entitlement is enforced yet; proposed 2/5 included agents require a tenant-scoped registry, measured costs and atomic activation limits first. Never claim those add-ons are currently deliverable.

## Staging acceptance, September 17, 2026

- Approved HTTPS host `staging-api.terrasatch.com` routes only `/api/v1/workspace/*` to isolated port 8012. Other paths, including admin, return 404. Existing production routes were preserved and production `/health` remained 200.
- Website Preview commit `608dc3d` is READY at https://wasatch-ascent-agrw0lv4v-k3y10s.vercel.app/workspace. Its branch-scoped backend setting is connected; the real sign-in screen was verified in the browser. Deployment protection remains enabled.
- API staging is deployed through `95465a7`. Real HTTPS/PostgreSQL tests passed secure cookies, login, tenant isolation, original-note readback, concurrent retry deduplication, and logout. Test accounts were disabled and their credentials cleared afterward. These tests ran directly against staging; Vercel protection prevented the unattended client from testing the full proxy flow.
- All 240 API tests passed for that deployment. The subsequent activation-email fix passed all 15 billing-safety tests, including four activation-state cases; it is not yet deployed to Oracle.
- The actual qwen3:1.7b model returned 27 tokens in 39.52 seconds. Full workspace chat timed out at 40 seconds with a truthful 503 and no saved answer. qwen3:0.6b has downloaded but its comparison test is pending. The running staging model container was temporarily capped at 0.5 CPU for comparison; compose still specifies 0.25 CPU, so the next operator must reconcile that deliberate temporary difference.
- D: disconnected and the temporary SSH key was cleaned up before the final model comparison. Restore the user-supplied key source before deploying further changes. Resend's current session lists QuakWrap only; TerraSatch email account/team selection is pending. No new Stripe mutations or production promotion occurred.


## Webhook implementation update — September 18, 2026

Stripe sandbox account `acct_1Txb0QPwzxCRGRdh` now has the v2 self-service catalog and an enabled staging webhook destination:

- Individual: `terrasatch_individual_monthly_v2` at $24/month.
- Team: `terrasatch_team_monthly_v2` at $399/month.
- Webhook endpoint: `we_1UH5K2PwzxCRGRdhQxNE0ddZ`.
- URL: `https://staging-api.terrasatch.com/api/v1/workspace/billing/stripe/webhook`.
- Events: `checkout.session.completed`, subscription created/updated/deleted/trial-will-end, `invoice.paid`, and `invoice.payment_failed`.
- Operations and Enterprise remain non-self-service and have no Checkout price.

The canonical production route remains `/api/v1/billing/stripe/webhook`. The workspace-prefixed alias is registered only when `TERRASATCH_ENV=staging`, allowing the existing staging Caddy policy to expose it without widening the production API surface.

Production continues to require normal Stripe HMAC signature verification. Isolated staging can instead verify test-mode events by retrieving the received `evt_*` directly from Stripe using the server-side test key and processing the provider-returned event. This fallback is allowed only when environment is staging, live billing is false, and the Stripe key is test-mode. The event ledger still provides replay/idempotency protection.

The staging Compose file now enables billing only in the isolated staging stack. Checkout success, cancellation, status polling, activation, and Customer Portal return URLs stay entirely on `staging-api.terrasatch.com` under `/api/v1/workspace/billing/*`, so sandbox acceptance does not depend on Vercel Preview protection. Transactional email remains the separate protected provider boundary. Secrets remain in the owner-only `.env.staging`; none are committed.

Deploy only from an isolated `feat/subscription-billing` worktree:

```bash
cd /path/to/isolated/subscription-billing-worktree
bash deploy/release-workspace-staging.sh
```

The script refuses `main`, refuses a dirty tracked worktree, loads `.env.staging`, migrates only the `terrasatch_staging` database, recreates only the `terrasatch-workspace-staging` API/worker, and verifies `127.0.0.1:8012/health/ready`.

Caddy reference: `deploy/examples/Caddyfile.workspace-staging`. It exposes only `/api/v1/workspace/*` from port 8012 and returns 404 elsewhere.

Do not describe the webhook as end-to-end accepted until the Oracle staging process is running the current branch head and an actual Stripe sandbox delivery has been observed successfully. Live billing remains disabled.


## Secretless sandbox Checkout lane — September 18, 2026

Oracle staging did not contain a TerraSatch Stripe test API key. Instead of copying or exposing an account secret, isolated staging now uses Stripe-hosted sandbox Payment Links while production retains the server-side Stripe API/HMAC design.

Sandbox Payment Links:
- Individual: `plink_1UH5n8PwzxCRGRdhckplOIz0`, $24/month, 30-day trial.
- Team: `plink_1UH5nAPwzxCRGRdhTJE7crl5`, $399/month, 30-day trial.
- Both redirect to the isolated staging success URL with `{CHECKOUT_SESSION_ID}`.
- TerraSatch appends a non-sensitive signup UUID using Stripe's supported `client_reference_id` URL parameter and locks the signup email with `locked_prefilled_email`.
- Payment Link metadata and subscription metadata are restricted to `product=terrasatch`, `billing_version=v2`, `environment=staging`, the expected plan code, and monthly cadence.

The staging webhook route is restricted in Caddy to Stripe's published webhook source IPv4 addresses and then re-validates `livemode=false`, event type, Payment Link ID, and TerraSatch metadata in the API. This reduced-auth mode exists only when `TERRASATCH_ENV=staging`, live billing is false, and the explicit staging Payment Link/Caddy trust flag is enabled. Production does not use this path and still requires normal Stripe signature verification.

Checkout completion provisions the signup using `client_reference_id` and the locked email. Subscription lifecycle events bind by the Stripe customer ID if no signup ID is present in static Payment Link metadata. If Stripe delivers the subscription event before Checkout completion, processing fails without recording the event so Stripe can retry after customer binding exists.

Transactional email remains optional only for isolated sandbox acceptance. The staging success page can recover the pending activation token by Checkout Session ID so Checkout -> webhook -> provisioning -> activation can be tested before the separate TerraSatch Resend account is ready.

Customer Portal remains a separate Stripe account configuration. The connected Stripe credential can read portal configurations but does not have permission to create one; no portal configuration currently exists in the TerraSatch sandbox.


## Transactional email structure — September 18, 2026

Billing lifecycle email no longer depends on GitHub Actions and does not require the Vercel Preview sender to be reachable.

Primary path:

```text
Stripe sandbox event
  -> TerraSatch API transaction
  -> billing_email_outbox
  -> supervised TerraSatch worker
  -> Resend API
  -> provider/message-ID receipt stored on outbox row
```

The worker checks the outbox every 15 seconds only when an email provider is configured. Direct Resend uses the same stable idempotency key for retries: `terrasatch-billing/<kind>/<stripe-event-id>`. Activation tokens are reconstructed from the stable activation signing secret only at send time; plaintext activation tokens are not stored in the outbox.

Required direct-provider settings, stored only in the owner-readable deployment environment:

- `TERRASATCH_RESEND_API_KEY`
- `TERRASATCH_BILLING_FROM`
- optional `TERRASATCH_BILLING_REPLY_TO`
- `TERRASATCH_BILLING_ACTIVATION_SIGNING_SECRET`

Fallback path:

```text
billing_email_outbox -> TerraSatch worker -> protected Vercel /api/billing-email -> Resend
```

The fallback remains compatible with `TERRASATCH_BILLING_EMAIL_WEBHOOK_URL` and `TERRASATCH_BILLING_EMAIL_WEBHOOK_SECRET`. The Vercel endpoint now returns the Resend message ID so the same outbox receipt fields are populated.

Migration `0015_billing_email_receipts` adds nullable `delivery_provider` and `provider_message_id` fields. Existing outbox rows remain valid.

GitHub Actions workflow files were removed from the billing branch intentionally. Validation is performed through the Oracle staging bootstrap and the manual browser acceptance script so field testing does not consume GitHub Actions minutes or introduce CI billing risk.

Live Stripe billing remains disabled. Transactional email work does not change `TERRASATCH_BILLING_ALLOW_LIVEMODE=false`.

Still required before public/live billing:
- Connect the separate TerraSatch Resend account and create a restricted sending API key.
- Verify the TerraSatch sending domain and chosen From address.
- Run one staging lifecycle email through Resend and confirm the stored provider message ID.
- Configure Resend delivery/bounce webhook reconciliation.
- Add operator-driven resend/password-reset flows.
- Finish Stripe Customer Portal configuration and live-mode security review.


Resend webhook routes:
- Production/canonical: `/api/v1/billing/resend/webhook`
- Isolated staging: `/api/v1/workspace/billing/resend/webhook`

Subscribe the Resend webhook to `email.sent`, `email.delivered`,
`email.delivery_delayed`, `email.bounced`, `email.complained`,
`email.failed`, and `email.suppressed`. TerraSatch verifies the raw request
using the Resend/Svix signing secret and a five-minute timestamp tolerance before
updating a matching `provider_message_id`. Unmatched events are acknowledged but
do not mutate billing state, which allows the same Resend account to carry other
TerraSatch email categories safely.


### Secure Oracle staging Resend setup

Use `deploy/configure-resend-workspace-staging.sh` after the TerraSatch Resend
account/domain exists. The helper:
- prompts for the Resend API key without terminal echo;
- optionally accepts the Resend webhook signing secret without terminal echo;
- writes only the four Resend/from/reply-to values into owner-readable
  `.env.staging` without putting secrets in shell history;
- validates the Compose configuration;
- restarts only the isolated staging API and worker;
- waits for local staging health;
- verifies the public Resend route is `400` for an unsigned request when the
  signing secret is configured, otherwise `404`;
- never changes `TERRASATCH_BILLING_ALLOW_LIVEMODE`.

Recommended staging webhook URL:
`https://staging-api.terrasatch.com/api/v1/workspace/billing/resend/webhook`

After configuration, rerun the standard staging bootstrap. Its safety summary now
reports direct Resend and delivery-reconciliation readiness independently.
