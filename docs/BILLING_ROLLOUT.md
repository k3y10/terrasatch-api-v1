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
2. Build from the billing branch in an isolated staging directory/database; never migrate production for a preview. Apply migrations through 0013 and run API and worker from the same version.
3. Configure a protected Preview origin and staging-only server credentials. Identify the public staging webhook origin before creating endpoints. No default production URL is acceptable for a sandbox acceptance run.
4. After explicit renewed Stripe authorization, verify account `acct_1Txb0QPwzxCRGRdh`, test mode, and create the matching v2 catalog. Configure customer portal cancellation/payment methods; plan switching needs separate backend validation.
5. Use a restricted Stripe key stored server-side and the matching webhook signing secret. Readiness also requires billing email URL/shared secret and activation signing secret. Never print credentials or commit environment files.
6. Verify Resend's sending domain and Preview-only `RESEND_API_KEY`, `TERRASATCH_BILLING_EMAIL_SECRET`, `TERRASATCH_BILLING_FROM`; the shared secret must match API `TERRASATCH_BILLING_EMAIL_WEBHOOK_SECRET`. Use the Preview email endpoint, success, cancellation and activation URLs.
7. Exercise Individual and Team signup → Checkout → signed webhook → committed subscription/outbox → inbox activation → workspace login → customer portal. Card required, $0 today, billing after 30 days unless canceled. Operations/Enterprise must reject checkout.
8. Test duplicate/concurrent/out-of-order webhooks, payment failures, cancellation, DB rollback, email retries, expired/consumed activation links, tenant isolation and CORS. Add password-reset/resend and email delivery-event handling before public release.
9. Confirm unit economics, retention semantics, support/hardware scope, tax registration/collection, subscription migration, and release base before requesting any production rollout.

Webhook event set: checkout.session.completed; customer.subscription.created/updated/deleted/trial_will_end; invoice.paid; invoice.payment_failed. Fresh subscription state and stale invoice ordering still need review. Live gate must remain false.

## Implemented safeguards and limits

Source/card data stays in its owning system: Stripe owns payment methods; TerraSatch owns tenant state and authorization. Browser inputs cannot select arbitrary Price IDs. Lookup key, amount, currency, cadence and subscription quantity are validated. Pending valid checkout is reused; near-expiry refresh remains an explicit retry conflict.

Email intents commit with billing state. Worker retries reconstruct the same activation token and stop ambiguous deliveries before Resend deduplication expires. Expired and consumed activations are held with `activation_expired` or `activation_consumed`; a token/signing-secret mismatch requires reconciliation. These terminal rows are not falsely marked sent and are not retried automatically. A replacement link requires a new explicit intent and provider idempotency key. Provider acceptance is not proof of inbox delivery. Operator reconciliation, resend and password reset remain open.

Sites, memberships, devices and channels have managed-plan checks. Processing-hour/retention allowances are not metered or pruned automatically. No new Satchy Agent or drone add-on entitlement is enforced yet; proposed 2/5 included agents require a tenant-scoped registry, measured costs and atomic activation limits first. Never claim those add-ons are currently deliverable.

## Staging acceptance, September 17, 2026

- Approved HTTPS host `staging-api.terrasatch.com` routes only `/api/v1/workspace/*` to isolated port 8012. Other paths, including admin, return 404. Existing production routes were preserved and production `/health` remained 200.
- Website Preview commit `608dc3d` is READY at https://wasatch-ascent-agrw0lv4v-k3y10s.vercel.app/workspace. Its branch-scoped backend setting is connected; the real sign-in screen was verified in the browser. Deployment protection remains enabled.
- API staging is deployed through `95465a7`. Real HTTPS/PostgreSQL tests passed secure cookies, login, tenant isolation, original-note readback, concurrent retry deduplication, and logout. Test accounts were disabled and their credentials cleared afterward. These tests ran directly against staging; Vercel protection prevented the unattended client from testing the full proxy flow.
- All 240 API tests passed for that deployment. The subsequent activation-email fix passed all 15 billing-safety tests, including four activation-state cases; it is not yet deployed to Oracle.
- The actual qwen3:1.7b model returned 27 tokens in 39.52 seconds. Full workspace chat timed out at 40 seconds with a truthful 503 and no saved answer. qwen3:0.6b has downloaded but its comparison test is pending. The running staging model container was temporarily capped at 0.5 CPU for comparison; compose still specifies 0.25 CPU, so the next operator must reconcile that deliberate temporary difference.
- D: disconnected and the temporary SSH key was cleaned up before the final model comparison. Restore the user-supplied key source before deploying further changes. Resend's current session lists QuakWrap only; TerraSatch email account/team selection is pending. No new Stripe mutations or production promotion occurred.
