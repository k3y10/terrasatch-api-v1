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

## Access policy

- Only authenticated TerraSatch users whose account email is under `@terrasatch.com` can open the
  email workspace.
- Owners and admins may view the internal TerraSatch inbox.
- Other internal members see mail addressed to their own portal account.
- A personal mailbox should use the same address on the person's portal user account so personal
  access resolves cleanly.
- `ops@terrasatch.com` is a shared send identity for admins/owners and does not need to be a login
  account.
- Internal users may send from their own mailbox.
- Admins and owners may also send from `ops@terrasatch.com`.
- A user cannot send as another person's mailbox.
- Incoming HTML is stored for archival fidelity, but the server-rendered portal displays escaped
  plain text. This avoids rendering untrusted email HTML in the workspace.
- Attachment metadata is stored. Attachment-byte download is intentionally not exposed in this
  first pass.

## Deploy

Use the normal Oracle production release path:

```bash
bash deploy/release-oracle.sh
```

The release applies Alembic migrations, so production must reach migration
`0022_workspace_email` before inbound delivery is enabled.

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

## Acceptance

After deployment and receiving configuration:

1. Send a test message from an external mailbox to an internal TerraSatch mailbox.
2. Confirm Resend records an `email.received` event and the webhook returns 2xx.
3. Open `/portal/email` and verify the message, subject, sender, plain-text body, and attachment
   metadata are present.
4. Reply from the workspace and verify the recipient receives the response from the selected
   TerraSatch mailbox.
5. Repeat inbound delivery for another internal personal mailbox if applicable.
6. Verify an internal user cannot send as another person's mailbox.
7. Verify an external/customer workspace account cannot open the internal email workspace.
8. Replay the Resend webhook and confirm the message is not duplicated.

Resend remains the delivery/receiving provider; PostgreSQL is the durable workspace copy used by
TerraSatch.
