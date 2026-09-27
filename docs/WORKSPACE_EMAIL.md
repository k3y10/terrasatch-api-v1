# Workspace Email

Receiving and attachment retrieval require a Resend key with Full access. A
send-only key cannot retrieve incoming email, even when DNS and the webhook are
verified. Set `TERRASATCH_RESEND_RECEIVING_API_KEY` in the server-only environment
to use a separate receiving key while retaining the restricted outbound key in
`TERRASATCH_RESEND_API_KEY`. If the separate key is absent, receiving retains the
existing API-key fallback for deployments already using a Full access key.
Never place either key in browser code, logs, source control, or public previews.

TerraSatch email is integrated into the existing Field Workspace instead of running a separate
mail server.

## Flow

```text
sender
  -> TerraSatch receiving/forwarding DNS
  -> Resend Receiving Emails
  -> existing signed Resend webhook
  -> TerraSatch API
  -> PostgreSQL workspace email tables
  -> /portal/email and /api/v1/workspace/organizations/{organization_id}/email
```

The production Resend webhook remains:

```text
POST https://api.terrasatch.com/api/v1/billing/resend/webhook
```

The same Svix verification used for delivery and bounce events protects `email.received`.
The webhook should retain the current delivery events and add `email.received`.

Resend's current API exposes a received message at:

```text
GET /emails/receiving/{email_id}
```

The signed webhook provides `data.email_id`; TerraSatch verifies the webhook before retrieving
and storing the complete message.

## Mailbox separation and access policy

Only authenticated TerraSatch users whose portal account is under `@terrasatch.com` can open the
email workspace. General organization roles do not grant blanket access to every executive mailbox.

| Mailbox | Default visibility | Human send policy | Purpose |
| --- | --- | --- | --- |
| personal user address, e.g. `keaton@terrasatch.com` | that user only | that user; explicit delegates may optionally send | executive/personal company mail |
| `support@terrasatch.com` | operator, admin, owner | operator, admin, owner | customer/user support |
| `ops@terrasatch.com` | admin, owner | admin, owner | company/field operations |
| `legal@terrasatch.com` | owner | owner | legal, contracts, privileged/sensitive correspondence |
| `billing@terrasatch.com` | admin, owner | read-only by default; owner can explicitly delegate send/reply | Stripe/billing lifecycle automation and billing visibility |

Personal mailboxes are private by default even when another user is an organization admin or owner.
A mailbox owner can explicitly delegate their own personal mailbox to another enabled internal
organization member with view-only or view-and-send access. Organization owners can explicitly
delegate shared company mailboxes. Delegation is additive and stored in
`workspace_email_delegates`; it does not change the user's general organization role.

Billing lifecycle automation continues to use the separate durable outbox. Human Billing replies require explicit send delegation and do not modify invoices or subscriptions.

A user cannot send as another person's mailbox unless that mailbox owner explicitly delegated send
permission. Incoming HTML is stored for archival fidelity, but the server-rendered portal displays
escaped plain text. This avoids rendering untrusted email HTML in the workspace.
- Incoming HTML is stored for archival fidelity, but the server-rendered portal displays escaped
  plain text. This avoids rendering untrusted email HTML in the workspace.
- Attachment metadata is stored, and authorized workspace users can open attachments through a
  TerraSatch route that retrieves a fresh Resend signed download URL after access checks.

## Deploy

Use the normal Oracle production release path:

```bash
bash deploy/release-oracle.sh
```

The release applies Alembic migrations, so production must reach migration
`0023_workspace_email_delegates` before inbound delivery is enabled. Migration
`0022_workspace_email` creates the durable message/read-state tables and `0023` adds explicit
mailbox delegation.

Do not enable receiving DNS first. Deploy and verify the API route/database before changing mail
routing.

## Resend

The existing production Resend webhook should add the `email.received` event while retaining its
current endpoint and signing secret.

Required server-side settings remain:

- `TERRASATCH_RESEND_API_KEY`
- `TERRASATCH_RESEND_WEBHOOK_SECRET`

The API key is needed because the inbound webhook is used as the signed notification/correlation
event and TerraSatch retrieves the complete received message from Resend before committing it to
PostgreSQL.

## Receiving domain / DNS

Configure Receiving Emails in the Resend dashboard and use the exact DNS records Resend shows for
the selected receiving setup.

Do **not** hard-code or blindly replace the root `terrasatch.com` MX records. If another mailbox
provider already receives TerraSatch email, replacing its MX records would redirect mail for every
`@terrasatch.com` address. Preserve the existing provider and use its forwarding/custom-domain
path when appropriate.

The repository intentionally does not encode an account-specific MX target because the correct
records must come from the active Resend receiving-domain configuration.


### Mail-provider coexistence

The TerraSatch workspace is an application inbox, not an IMAP server. If `@terrasatch.com` is
already hosted by Google Workspace, Microsoft 365, or another mailbox provider, keep that provider
as the root MX and forward the required addresses into Resend/TerraSatch. This preserves ordinary
mail-client access while giving TerraSatch a durable application copy for Satchy/workspace
workflows.

Only move the root MX to Resend if TerraSatch intentionally wants the application to become the
primary receiver for every `@terrasatch.com` mailbox. Personal executive addresses should not be
made dependent on an MX cutover merely to enable the workspace inbox.

## Acceptance

After deployment and receiving configuration:

1. Send a test message from an external mailbox to an internal TerraSatch mailbox.
2. Confirm Resend records an `email.received` event and the webhook returns 2xx.
3. Open `/portal/email` and verify the message, subject, sender, plain-text body, and attachment
   metadata are present.
4. Open a test attachment and confirm TerraSatch authorizes the request before redirecting to the
   fresh Resend signed download URL.
5. Reply from the workspace and verify the recipient receives the response from the selected
   TerraSatch mailbox.
6. Repeat inbound delivery for another internal personal mailbox if applicable.
7. Verify an internal user cannot send as another person's mailbox.
8. Verify an external/customer workspace account cannot open the internal email workspace.
9. Replay the Resend webhook and confirm the message is not duplicated.

Resend remains the delivery/receiving provider; PostgreSQL is the durable workspace copy used by
TerraSatch.


## Delegation UI

The human workspace at `/portal/email` includes a **Mailbox Access** panel for mailboxes the signed-in
user is allowed to manage. Personal mailbox owners can grant/revoke view-only or view-and-send
access. Organization owners can manage shared mailbox delegation. The panel makes
Billing read-only by default and offers explicit owner-granted human send permission.

## Delegation API

Mailbox delegation is organization-scoped and only accepts enabled internal TerraSatch members.

- `GET /api/v1/workspace/organizations/{organization_id}/email-access/delegations?mailbox=...`
- `POST /api/v1/workspace/organizations/{organization_id}/email-access/delegations`
- `POST /api/v1/workspace/organizations/{organization_id}/email-access/delegations/revoke`

Create/update payload:

```json
{
  "mailbox": "keaton@terrasatch.com",
  "delegate_email": "ericka@terrasatch.com",
  "can_send": false
}
```

Personal mailbox delegation can only be managed by the owner of that mailbox. Shared mailbox
delegation can only be managed by an organization owner. Billing send/reply requires an explicit owner-granted delegation.

## Operational boundary

Stripe billing remains:

```text
Stripe lifecycle event
  -> TerraSatch subscription/billing service
  -> durable billing email outbox
  -> Oracle worker
  -> Resend send API
  -> Resend delivery/bounce event
  -> signed TerraSatch Resend webhook
  -> billing outbox delivery state
```

Human/inbound email remains:

```text
external sender
  -> Resend Receiving
  -> email.received
  -> signed TerraSatch Resend webhook
  -> workspace email storage
  -> mailbox policy/delegation
  -> /portal/email
```

Both paths intentionally share Resend transport and webhook verification but do not share human
mailbox authorization or billing-send authority.

## Daily workspace and organization boundary

Set `TERRASATCH_WORKSPACE_EMAIL_ORGANIZATION_ID` to the trusted internal organization UUID. Both portal and JSON email routes fail closed if it is missing or a different organization is selected. A matching email domain alone does not grant access. Existing role defaults above apply only inside this organization. Explicit grants are additive; removing a grant does not remove access already granted by a member's role.

`satchy@terrasatch.com` is an owner/admin shared sender; owners may delegate it. It supports reviewed human messages, not unattended campaigns. Marketing audiences, consent/unsubscribe handling, scheduling, and automatic support sending remain disabled/unimplemented.

The inbox has Inbox/Sent/All mail filters, an assigned-mailbox selector, and search over the latest bounded set of messages. The From selector includes only send-authorized mailboxes. Personal mail remains private unless its owner delegates it.

Draft with Satchy prepares a support reply through the configured private Ollama service. The endpoint checks organization, message visibility, send/reply permission, CSRF, and rate limits. It releases its database session before model inference. Drafts never send automatically and cannot execute tools. Users must verify facts and explicitly send. Model availability is required; manual replies remain available if inference fails.

The workspace Satchy rail uses the existing authenticated chat API. Panel preferences and work context are saved per organization/user. Map panels load external OpenStreetMap only after selecting a recorded location. Briefings reflect stored workspace snapshots; Monday.com and calendar ingestion are not connected by this change.

### Monday internal pilot

`TERRASATCH_WORKSPACE_MONDAY_API_TOKEN` is stored only in the server environment. `TERRASATCH_WORKSPACE_MONDAY_BOARD_IDS` is a comma-separated allowlist, maximum eight numeric IDs. The connector uses a fixed Monday HTTPS endpoint and read-only GraphQL query. Each board is limited to 100 tasks; the interface shows the first 20 and labels partial results. No polling or writes occur. Routes require membership in the configured internal organization and admin/owner role. Summary requests also require CSRF and are rate limited; model output cannot execute actions. Personal Monday tokens mirror the user's Monday access, so use a suitably restricted account. No credential is returned to the browser.


### Internal team setup and beta connection manager

The portal Account & access panel provides owner-only internal team account creation.
It creates a new @terrasatch.com identity with Viewer or Operator access, enforcing
subscription seats and server capacity. Existing identities cannot be reset or claimed
through this form. The owner supplies an initial password and shares it securely; no
invitation is sent. Shared-mailbox delegation stays in Email. Domain receiving and
a member's ability to sign in are separate states.

Tools & services defaults to ready/connected adapters, with search and filters for
platform setup and planned providers. Connection setup uses existing scoped API
requests, OAuth authorization, encrypted manual credentials, tests, and revocation.
Provider app registration is still required for OAuth services; no installed adapter
implies access to a customer's provider account. Public endpoint and credential
validation remain server-side. Staging's encryption key is persisted in its restricted
environment file and must be preserved across releases.


### Installable workspace frame

The workspace uses a fixed header/footer with independently scrolling content and
optional navigation/Satchy panels. Panel visibility is a local device preference;
module access and mailbox permissions remain server-controlled. Small screens use
closable drawers. Existing vendor icons are vendored from the website asset set,
with source provenance retained in the static integration directory.

The PWA manifest starts at /portal and registers a narrowly handled service worker.
Only the public offline page and brand icon are cached. Authenticated HTML, email,
API responses, and mutations are network-only; offline sending is not queued.
Installation is browser-dependent and is not equivalent to offline access to mail.
