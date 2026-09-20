# External integrations

TerraSatch treats an integration as a tenant-scoped connection, not as a logo or a browser-stored token. Connections can be personal, team-scoped, or organization-scoped. Personal connections are visible to the owning member; team and organization connections require an owner or administrator to manage.

## Credential boundary

Provider passwords, API keys, OAuth access tokens, refresh tokens, private keys, and Slack webhook URLs must never be sent to the browser integration form or stored in `integration_connections.configuration`. OAuth credentials are obtained by the API callback, encrypted with Fernet, and stored in `integration_credentials`. The connection table holds only an opaque `credential_ref` and safe provider account metadata.

Generate the encryption key once per deployment and keep it stable:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Set that value only on the API/worker host as `TERRASATCH_INTEGRATION_ENCRYPTION_KEY`. Do not put it in Vercel `VITE_*` variables.

## Google Drive

The first Drive adapter uses the narrow `https://www.googleapis.com/auth/drive.file` scope. This lets TerraSatch work with files the user explicitly creates, opens, or shares with the app rather than granting blanket access to the entire Drive.

1. Create a Google Cloud OAuth client of type **Web application**.
2. Enable the Google Drive API.
3. Configure the OAuth consent screen and the `drive.file` scope.
4. Register the exact redirect URI: `https://api.terrasatch.com/api/v1/workspace/integrations/oauth/google_drive/callback`.
5. Set the server-only client ID, client secret, and redirect URI environment values.

The authorization request uses a random single-use `state`, requests offline access, and stores any refresh token only in the encrypted credential record.

## Slack

The initial Slack adapter deliberately requests only the `incoming-webhook` scope so the installing workspace chooses the destination explicitly and TerraSatch does not receive broad message-history access.

1. Create the TerraSatch Slack app and configure OAuth & Permissions.
2. Add the `incoming-webhook` bot scope.
3. Register the exact redirect URI: `https://api.terrasatch.com/api/v1/workspace/integrations/oauth/slack/callback`.
4. Set the server-only Slack client ID, client secret, and redirect URI environment values.
5. Distribute or approve the app as required before installing it into customer workspaces.

Slack code exchange uses HTTP Basic authentication for the client credentials. Returned bot tokens, refresh tokens when rotation is enabled, and incoming webhook URLs stay inside the encrypted credential payload.

## Lifecycle

`requested -> awaiting_authorization -> connected`

A failed provider exchange or connection test moves the record to `error`. A successful provider revocation deletes the encrypted credential and marks the connection `revoked`. OAuth state values are stored only as SHA-256 digests, expire quickly, and are single-use.

Roadmap providers remain `planned` until their server adapter and deployment configuration actually exist.


## First provider output operations

Connected providers now expose two server-side output primitives that keep credentials out of the browser:

- Slack: send a text notification through the channel-specific incoming webhook returned during OAuth.
- Google Drive: create a UTF-8 text, Markdown, CSV, or JSON file using a multipart Drive upload. A configured `folder_id` is used as the file parent.

Every provider output requires a caller-supplied UUID request ID. TerraSatch creates a durable pending delivery record before contacting the provider, stores only a content hash/size plus safe response metadata, and returns the existing delivery for a repeated request ID. This avoids silently retrying a communication that may already have reached an external system.

Shared team integrations remain administrator-visible in the member portal until TerraSatch has an explicit portal team-membership mapping. This is intentionally conservative: team connection metadata is not exposed to every organization member merely because they share the same organization.
