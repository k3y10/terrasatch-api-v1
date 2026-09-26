# Workspace Email

TerraSatch email is integrated into the existing Field Workspace instead of running a separate
mail server.

## Flow

```text
sender
  -> terrasatch.com MX
  -> Resend inbound
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
Do not create a second production webhook unless a separate signing secret is also configured.

## Access policy

- Only authenticated TerraSatch users whose account email is under `@terrasatch.com` can open the
  email workspace.
- Owners and admins may view the internal TerraSatch inbox.
- Operators may view their own mailbox.
- Operators, admins, and owners may send from their own mailbox.
- Admins and owners may also send from the shared `ops@terrasatch.com` mailbox.
- A user cannot send as another person's mailbox.
- Incoming HTML is stored for archival fidelity, but the server-rendered portal displays escaped
  plain text. This avoids rendering untrusted email HTML in the workspace.

## Deploy

Use the normal Oracle production release path:

```bash
bash deploy/release-oracle.sh
```

The release applies Alembic migrations, so production must reach migration
`0022_workspace_email` before inbound delivery is enabled.

Do not enable DNS first. Deploy and verify the API route/database before changing MX.

## Resend

The existing production Resend webhook should add the `email.received` event while retaining its
current endpoint and signing secret.

The API already requires the Resend API key because an inbound webhook contains metadata only; the
handler retrieves the full received message from Resend before committing it to PostgreSQL.

## DNS

After the deployment and webhook are verified, enable Resend inbound routing for the root domain.
The record prepared during setup was:

```text
Type:     MX
Host:     @
Target:   inbound-smtp.us-east-1.amazonaws.com
Priority: 10
TTL:      30 minutes
```

Before saving, confirm there is no existing production MX provider that must continue receiving
mail. Changing the root MX changes inbound delivery for all `@terrasatch.com` addresses.

## Acceptance

After DNS propagates:

1. Send a test message from an external mailbox to `keaton@terrasatch.com`.
2. Confirm Resend records an `email.received` event and the webhook returns 2xx.
3. Open `/portal/email` and verify the message, subject, sender, plain-text body, and attachment
   metadata are present.
4. Reply from the workspace and verify the recipient receives the message from
   `keaton@terrasatch.com`.
5. Repeat inbound delivery for `ericka@terrasatch.com` and `ops@terrasatch.com`.
6. Verify an internal user cannot send as another person's mailbox.
7. Verify an external/customer workspace account cannot open the internal email workspace.

Resend remains the delivery/receiving provider; PostgreSQL is the durable workspace copy used by
TerraSatch.
