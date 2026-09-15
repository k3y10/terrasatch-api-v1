# TerraSatch subscription billing rollout

This document describes the safe rollout order for the self-service TerraSatch subscription system.

## Safety defaults

- `TERRASATCH_BILLING_ENABLED=false` by default.
- `TERRASATCH_BILLING_ALLOW_LIVEMODE=false` is a second, independent production gate.
- Existing pilot and legacy organizations are not converted into managed subscriptions automatically.
- Existing Edge heartbeat, radio ingest, preserved source traffic, and operational history are not disabled when billing becomes restricted.
- Managed-plan restrictions apply to new configuration and reactivation of capacity-limited resources.
- Stripe remains the system of record for payment methods. TerraSatch never stores card data.
- Stripe product/price IDs are resolved server-side from stable lookup keys. Browser clients never submit Stripe Price IDs.

## Subscription catalog

The canonical catalog lives in `src/terrasatch/billing/plans.py` and is exposed publicly at:

`GET /api/v1/billing/plans`

The website consumes this endpoint instead of maintaining an independent pricing table.

Self-service plans currently use a 30-day trial and collect a payment method through Stripe Checkout before the trial begins.

## Required Stripe test-mode setup

Use the TerraSatch Stripe account only. Do not configure TerraSatch products in the QuakWrap Stripe account.

Create one recurring monthly and annual Price for each self-service plan using these lookup keys:

| Plan | Monthly lookup key | Annual lookup key |
| --- | --- | --- |
| Field | `terrasatch_field_monthly_v1` | `terrasatch_field_annual_v1` |
| Team | `terrasatch_team_monthly_v1` | `terrasatch_team_annual_v1` |
| Operations | `terrasatch_operations_monthly_v1` | `terrasatch_operations_annual_v1` |

Configure Stripe Customer Portal for subscription cancellation and payment-method management.

Create a test-mode webhook endpoint pointing to:

`https://api.terrasatch.com/api/v1/billing/stripe/webhook`

Subscribe it to at least:

- `checkout.session.completed`
- `customer.subscription.created`
- `customer.subscription.updated`
- `customer.subscription.deleted`
- `customer.subscription.trial_will_end`
- `invoice.paid`
- `invoice.payment_failed`

Store the test secret key and webhook signing secret only in the API deployment environment.

## Required Resend/Vercel setup

Verify the TerraSatch sending domain in Resend before enabling lifecycle email.

Configure these Vercel server-only variables on the website project:

- `RESEND_API_KEY`
- `TERRASATCH_BILLING_EMAIL_SECRET`
- `TERRASATCH_BILLING_FROM`

Configure matching API variables:

- `TERRASATCH_BILLING_EMAIL_WEBHOOK_URL=https://terrasatch.com/api/billing-email`
- `TERRASATCH_BILLING_EMAIL_WEBHOOK_SECRET=<same random secret used by Vercel>`

Activation tokens are delivered in the URL fragment (`#token=...`) so they are not included in the normal HTTP request URL sent to Vercel.

## Recommended rollout order

1. Merge and deploy the API with billing disabled.
2. Run migration `0011_subscription_billing` and confirm API health.
3. Configure the TerraSatch Stripe account in test mode.
4. Configure Resend/Vercel server-only environment variables.
5. Enable `TERRASATCH_BILLING_ENABLED=true` while keeping `TERRASATCH_BILLING_ALLOW_LIVEMODE=false`.
6. Exercise Field, Team, and Operations Checkout flows in Stripe test mode.
7. Verify account provisioning, activation email, portal login, Edge service payload, Customer Portal, cancellation, payment failure grace, and webhook replay idempotency.
8. Merge/deploy the website subscription UI after the API test deployment is confirmed.
9. Complete tax, terms, refund/cancellation, support, and production billing review.
10. Only after the production review, add live Stripe credentials and explicitly set `TERRASATCH_BILLING_ALLOW_LIVEMODE=true`.

## Entitlement enforcement in this release

Server-enforced managed-plan limits cover:

- enabled sites
- enabled organization memberships
- enabled Edge devices
- enabled monitored channels
- restricted subscription state blocking new configuration

Processing-hour allowances and historical-retention values are represented in the catalog but are not usage-metered or automatically pruned in this release. They must not be treated as automated usage billing or destructive retention policy until a dedicated metering/retention implementation is reviewed.
