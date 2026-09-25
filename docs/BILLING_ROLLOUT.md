# TerraSatch subscription rollout — preview only

Do not merge, promote, enable live billing, or modify Stripe under the current pricing request.

## Catalog

`src/terrasatch/billing/plans.py` exposes `/api/v1/billing/plans`. Keep it aligned with the website's `src/lib/plan-catalog.ts`; the website retains pricing when the API is unavailable.

| Plan | Public monthly price | Checkout | Planned lookup key |
| --- | --- | --- | --- |
| Individual | $24 | 14-day payment-method-required trial, when enabled | `terrasatch_individual_monthly_v2` |
| Team | $399 | 14-day payment-method-required trial, when enabled | `terrasatch_team_monthly_v2` |
| Operations | From $1,999 | Sales/scoped only | None |
| Enterprise | Custom | Sales/scoped only | None |

Annual values are null. Optional annual discounts remain proposals. Old pitch-model prices are internal financial assumptions, not public minimums. The v2 keys deliberately differ from the already-created $49/$500 v1 sandbox prices; do not reuse or transfer the old lookup keys. Do not automatically migrate existing subscriptions.

## Gates and deployment order

1. Keep billing disabled and live mode false. Keep both PRs draft.
2. Build from the billing branch in an isolated staging directory/database; never migrate production for a preview. Apply migrations through 0017 and run API and worker from the same version.
3. Configure a protected Preview origin and staging-only server credentials. Identify the public staging webhook origin before creating endpoints. No default production URL is acceptable for a sandbox acceptance run.
4. After explicit renewed Stripe authorization, verify account `acct_1Txb0QPwzxCRGRdh`, test mode, and create the matching v2 catalog. Configure customer portal cancellation/payment methods; plan switching needs separate backend validation.
5. Production Stripe still requires a server-side restricted key and matching webhook signing secret. Staging and production billing readiness both require the direct Oracle-to-Resend sender plus signed Resend delivery reconciliation; the Vercel sender is resilience fallback only and cannot satisfy readiness by itself. Never print credentials or commit environment files.
6. The separate TerraSatch Resend account now owns domain `terrasatch.com` (domain ID `5876992d-002a-4b26-b53c-0c7e29f33b8f`) and staging webhook `76225e17-36a9-4dc9-95a4-b28094a26d4d`. Preferred delivery is Oracle worker -> Resend using owner-only `TERRASATCH_RESEND_API_KEY`, `TERRASATCH_BILLING_FROM=TerraSatch Billing <billing@terrasatch.com>`, and `TERRASATCH_BILLING_REPLY_TO=support@terrasatch.com`. The protected Vercel `/api/billing-email` endpoint remains fallback-only.
7. Exercise Individual and Team signup → Checkout → signed webhook → committed subscription/outbox → inbox activation → workspace login → customer portal. Card required, $0 today, billing after 30 days unless canceled. Operations/Enterprise must reject checkout.
8. Test duplicate/concurrent/out-of-order webhooks, payment failures, cancellation, DB rollback, email retries, expired/consumed activation links, tenant isolation and CORS. Provider/message-ID receipt tracking and Resend sent/delivered/delayed/bounce/complaint/failure/suppression reconciliation are implemented. Password reset and activation resend now use the same durable outbox and signed delivery reconciliation.
9. Confirm unit economics, retention semantics, support/hardware scope, tax registration/collection, subscription migration, and release base before requesting any production rollout.

Webhook event set: checkout.session.completed; customer.subscription.created/updated/deleted/trial_will_end; invoice.paid; invoice.payment_failed. Subscription and invoice state now record Stripe event-created watermarks so older delayed events are ledgered but cannot overwrite newer state or enqueue stale customer email. The current branch still requires Oracle staging acceptance of these guards. Live gate must remain false.

## Implemented safeguards and limits

Source/card data stays in its owning system: Stripe owns payment methods; TerraSatch owns tenant state and authorization. Browser inputs cannot select arbitrary Price IDs. Lookup key, amount, currency, cadence and subscription quantity are validated. Pending valid checkout is reused; near-expiry refresh remains an explicit retry conflict.

Email intents commit with billing state. The worker prefers direct Resend delivery and uses the protected Vercel sender only as a fallback. Retries reconstruct the same activation token and reuse the same provider idempotency key. Provider acceptance stores the Resend message ID in `billing_email_outbox`; signed Resend webhooks then reconcile sent, delivered, delayed, bounced, complained, failed, and suppressed outcomes. Expired and consumed activations are held with `activation_expired` or `activation_consumed`; a token/signing-secret mismatch requires reconciliation. These terminal rows are not falsely marked sent and are not retried automatically. `billing email-status` exposes safe outbox state in the admin console without recipient/context data. Password reset and activation resend are durable account-email flows. Reset tokens are single-use, purpose-bound, short-lived, and reconstructed only at send time; plaintext reset tokens are not stored in the outbox.

Sites, memberships, devices and channels have managed-plan checks. Processing-hour/retention allowances are not metered or pruned automatically. No new Satchy Agent or drone add-on entitlement is enforced yet; proposed 2/5 included agents require a tenant-scoped registry, measured costs and atomic activation limits first. Never claim those add-ons are currently deliverable.

## Staging acceptance, September 17, 2026

- Approved HTTPS host `staging-api.terrasatch.com` routes only `/api/v1/workspace/*` to isolated port 8012. Other paths, including admin, return 404. Existing production routes were preserved and production `/health` remained 200.
- Website Preview commit `608dc3d` is READY at https://wasatch-ascent-agrw0lv4v-k3y10s.vercel.app/workspace. Its branch-scoped backend setting is connected; the real sign-in screen was verified in the browser. Deployment protection remains enabled.
- API staging is deployed through `95465a7`. Real HTTPS/PostgreSQL tests passed secure cookies, login, tenant isolation, original-note readback, concurrent retry deduplication, and logout. Test accounts were disabled and their credentials cleared afterward. These tests ran directly against staging; Vercel protection prevented the unattended client from testing the full proxy flow.
- All 240 API tests passed for that deployment. The subsequent activation-email fix passed all 15 billing-safety tests, including four activation-state cases; it is not yet deployed to Oracle.
- The actual qwen3:1.7b model returned 27 tokens in 39.52 seconds. Full workspace chat timed out at 40 seconds with a truthful 503 and no saved answer. qwen3:0.6b has downloaded but its comparison test is pending. The running staging model container was temporarily capped at 0.5 CPU for comparison; compose still specifies 0.25 CPU, so the next operator must reconcile that deliberate temporary difference.
- D: disconnected and the temporary SSH key was cleaned up before the final model comparison. Restore the user-supplied key source before deploying further changes. No production promotion occurred.


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
- Individual: `plink_1UJTVMPwzxCRGRdhzpdBiKN7`, $24/month, 14-day trial.
- Team: `plink_1UJTVNPwzxCRGRdhoMTBEZRx`, $399/month, 14-day trial.
- Both redirect to the isolated staging success URL with `{CHECKOUT_SESSION_ID}`.
- TerraSatch appends a non-sensitive signup UUID using Stripe's supported `client_reference_id` URL parameter and locks the signup email with `locked_prefilled_email`.
- Payment Link metadata and subscription metadata are restricted to `product=terrasatch`, `billing_version=v2`, `environment=staging`, the expected plan code, and monthly cadence.

The staging webhook route is restricted in Caddy to Stripe's published webhook source IPv4 addresses and then re-validates `livemode=false`, event type, Payment Link ID, and TerraSatch metadata in the API. This reduced-auth mode exists only when `TERRASATCH_ENV=staging`, live billing is false, and the explicit staging Payment Link/Caddy trust flag is enabled. Production does not use this path and still requires normal Stripe signature verification.

Checkout completion provisions the signup using `client_reference_id` and the locked email. Subscription lifecycle events bind by the Stripe customer ID if no signup ID is present in static Payment Link metadata. If Stripe delivers the subscription event before Checkout completion, processing fails without recording the event so Stripe can retry after customer binding exists.

Transactional email is no longer optional in isolated staging readiness. The staging success page still supports activation recovery for diagnostics, but `billing_is_configured` now remains false until an email sender and signed Resend delivery webhook reconciliation are both configured.

Customer Portal is now configured in the TerraSatch sandbox with default configuration `bpc_1UHAGBPwzxCRGRdhBmPQexBm`. It allows payment-method updates, invoice history, and cancellation at period end with cancellation reasons. Customer profile/email updates, subscription plan changes, quantity changes, and the hosted shareable login page remain disabled so TerraSatch stays authoritative for identity and entitlements. A sandbox Portal session was created successfully for the existing TerraSatch test customer using the default configuration.


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

Account recovery uses the same queue. `password_reset` rows reference a short-lived reset intent ID; the worker reconstructs the purpose-separated HMAC token only when sending and builds the reset URL from `TERRASATCH_API_BASE_URL`. `activation_resend` reuses a valid pending activation or creates a fresh one after expiry. Public recovery forms intentionally return the same response whether an email exists or not.

Required direct-provider settings, stored only in the owner-readable deployment environment:

- `TERRASATCH_RESEND_API_KEY`
- `TERRASATCH_BILLING_FROM`
- optional `TERRASATCH_BILLING_REPLY_TO`
- `TERRASATCH_BILLING_ACTIVATION_SIGNING_SECRET`

Fallback path:

```text
billing_email_outbox -> TerraSatch worker -> protected Vercel /api/billing-email -> Resend
```

The fallback remains compatible with `TERRASATCH_BILLING_EMAIL_WEBHOOK_URL` and `TERRASATCH_BILLING_EMAIL_WEBHOOK_SECRET`, but it is not configured in isolated staging and cannot satisfy staging/production readiness by itself. The Vercel endpoint returns the Resend message ID so the same outbox receipt fields are populated when fallback is explicitly enabled for recovery.

Migration `0015_billing_email_receipts` adds provider receipt/reconciliation fields. Migration `0016_account_recovery_email` adds credential-version and password-reset intent state. Migration `0017_stripe_event_ordering` adds nullable Stripe event-created watermarks to subscription/invoice state and the event ledger. Existing rows remain valid and acquire watermarks as new Stripe events are processed.

GitHub Actions workflow files were removed from the billing branch intentionally. Validation is performed through the Oracle staging bootstrap and the manual browser acceptance script so field testing does not consume GitHub Actions minutes or introduce CI billing risk.

Live Stripe billing remains disabled. Transactional email work does not change `TERRASATCH_BILLING_ALLOW_LIVEMODE=false`.

Still required before public/live billing:
- Run the standard isolated Oracle bootstrap on the current branch head and require lock validation, Ruff, the full pytest suite, migration through `0017`, Caddy checks, and clean staging logs.
- Run one real staging password-reset email and one activation-resend email through the verified `billing@terrasatch.com` sender and confirm signed delivery reconciliation.
- Run one final Stripe sandbox Checkout -> webhook -> password creation -> automatic Field Workspace handoff on the current branch head.
- Exercise delayed/out-of-order subscription and invoice events against staging and confirm stale events do not mutate current state or enqueue customer email.
- Visually confirm the Field Workspace recovery screens and login handoff.
- Re-run the authenticated TerraSatch Portal route against current staging and confirm it opens the configured sandbox Customer Portal; live-mode security review remains separate.


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
domain is verified. The helper:
- prompts only for the dedicated Resend Sending Access key and Full Access admin key, both without terminal echo;
- asks Resend to verify domain ID `5876992d-002a-4b26-b53c-0c7e29f33b8f` and refuses to continue unless `terrasatch.com` is `verified`;
- rotates webhook `76225e17-36a9-4dc9-95a4-b28094a26d4d`'s signing secret through the Resend API and captures it without printing it;
- persists only the sending key, webhook signing secret, `TerraSatch Billing <billing@terrasatch.com>`, and `support@terrasatch.com` into owner-readable `.env.staging`;
- never persists the Full Access admin key;
- validates Compose, restarts only the isolated staging API/worker, waits for health, and requires the unsigned public webhook request to return `400`;
- never changes `TERRASATCH_BILLING_ALLOW_LIVEMODE`.

Recommended staging webhook URL:
`https://staging-api.terrasatch.com/api/v1/workspace/billing/resend/webhook`

### TerraSatch Resend sending domain

Resend domain ID: `5876992d-002a-4b26-b53c-0c7e29f33b8f`  
Authoritative DNS: GoDaddy (`ns25.domaincontrol.com`, `ns26.domaincontrol.com`)  
Required sender: `TerraSatch Billing <billing@terrasatch.com>`

The domain was provisioned and verified in Resend on September 18, 2026. The provider-issued records remain documented below for operational recovery:

| Capability | DNS type | Name | Value / target | Priority |
| --- | --- | --- | --- | --- |
| DKIM | TXT | `resend._domainkey` | `p=MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCs0cvPwKPpM5UxQzEuxS8CQ5hKz1sNTy3bUOg83UTmKtgAdBI3IDpAL4xtJhSmQfKYY6mFqUfXBUi0M5QEkzmrWSoCWQliHsuGOGLXBcbA3EGGrdjE8fp0ZbmhS+H5362efFltMOSJ75dtsOOhbxzF9JkPEKhlsPhRhp0FGMH5GQIDAQAB` | — |
| SPF | MX | `send` | `feedback-smtp.us-east-1.amazonses.com` | 10 |
| SPF | TXT | `send` | `v=spf1 include:amazonses.com ~all` | — |
| SPF | CNAME | `rsend` | `send.forge.rmta.net` | — |

Do not use `onboarding@resend.dev`, test-domain senders, or unverified From addresses in TerraSatch billing acceptance. Staging and production both fail readiness until signed Resend delivery reconciliation is configured.

After configuration, rerun the standard staging bootstrap. Its safety summary now
reports direct Resend and delivery-reconciliation readiness independently.


## Stablecoin invoice subscriptions — September 25, 2026

TerraSatch supports a non-custodial, non-private-preview recurring crypto path through Stripe Billing:

- `POST /api/v1/billing/crypto-subscription` creates the same TerraSatch signup intent used by card Checkout.
- The API creates a Stripe Customer and a normal recurring Subscription with `collection_method=send_invoice`.
- The subscription uses the same server-owned v2 Price lookup key, a 14-day trial, and TerraSatch `signup_id`, plan, interval, environment, and `payment_rail=crypto_invoice` metadata.
- Stripe generates recurring hosted invoices. Eligible customers can choose Crypto/stablecoins on the invoice and approve each payment from their wallet.
- This path does **not** pretend to perform silent recurring wallet debits. Automatic off-session stablecoin withdrawal remains dependent on Stripe's separate recurring-stablecoin capability/private preview.
- The existing `customer.subscription.*` and `invoice.*` webhook pipeline remains the source of truth for workspace provisioning and service access. A subscription that passes its invoice due date becomes `past_due`, so TerraSatch's existing grace/restricted entitlement behavior applies without a second billing state machine.
- The default crypto invoice payment window is three days and is configurable through `TERRASATCH_BILLING_CRYPTO_INVOICE_DAYS_UNTIL_DUE`.
- Staging requires a server-side restricted Stripe test key for this route. Static Payment Links remain available for ordinary sandbox Checkout, but cannot create this send-invoice subscription on behalf of the API.

Do not enable Stripe Tax automatically until TerraSatch has the applicable tax registration(s). Stablecoin is a payment method; taxability follows the underlying TerraSatch product and customer jurisdiction.
