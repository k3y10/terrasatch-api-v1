# Workspace Email

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
| `billing@terrasatch.com` | admin, owner | **human sending disabled** | Stripe/billing lifecycle automation and billing visibility |

Personal mailboxes are private by default even when another user is an organization admin or owner.
A mailbox owner can explicitly delegate their own personal mailbox to another enabled internal
organization member with view-only or view-and-send access. Organization owners can explicitly
delegate shared company mailboxes. Delegation is additive and stored in
`workspace_email_delegates`; it does not change the user's general organization role.

`billing@terrasatch.com` is intentionally different: the existing Stripe/billing outbox owns
billing lifecycle sending. Human workspace users may be granted visibility, but the workspace will
not send manually as `billing@`. This keeps billing automation, idempotency, retries, and
delivery/bounce reconciliation isolated from normal human correspondence.

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
`billing@terrasatch.com` explicitly view-only and never offers human send permission.

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
delegation can only be managed by an organization owner. Any requested send permission for
`billing@terrasatch.com` is forced off.

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
