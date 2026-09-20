# External integrations

TerraSatch treats an integration as a tenant-scoped connection, not as a logo or a browser-stored token. Connections can be personal, team-scoped, or organization-scoped. Personal connections are visible to the owning member; team and organization connections require an owner or administrator to manage.

## Credential boundary

## Provider registry and connection experience

The API now separates three questions that the client can present directly: whether a provider is
supported by TerraSatch, whether this deployment is configured to connect it, and whether the
current member is allowed to connect it at personal, team, or organization scope. Catalog responses
also include visible connected scopes and human labels for runtime capabilities. This lets clients
render states such as **Connected**, **Available**, **Needs admin**, and **Coming soon** without
recreating authorization policy in the frontend.

Platform OAuth application secrets are resolved through one provider-config boundary. The preferred
deployment input is a single server-only `TERRASATCH_INTEGRATION_PROVIDER_CONFIG_JSON` secret
bundle, which can be injected from OCI Vault or another deployment secret store. Existing
per-provider environment variables remain only as a compatibility fallback. Customer access tokens,
refresh tokens, webhook URLs, and account credentials are never stored in this bundle; those stay
encrypted per connection in `integration_credentials`.

Provider secrets are never returned to the browser or stored in `integration_connections.configuration`.
OAuth credentials are obtained by the API callback. CalTopo service-account credentials and Snowflake
PATs are submitted once through the protected credential setup endpoint for providers that do not
offer the same OAuth experience. All customer secrets are immediately encrypted with Fernet and
stored in `integration_credentials`. The connection table holds only an opaque `credential_ref`
and safe provider account metadata.

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
5. Store the client ID, client secret, and redirect URI in the server-only provider config bundle
   (or the legacy per-provider environment fallback).

The authorization request uses a random single-use `state`, requests offline access, and stores any refresh token only in the encrypted credential record.

Drive exports use multipart `files.create` requests and set `supportsAllDrives=true`. That keeps the same export path compatible with My Drive and Shared Drive destinations when the authenticated user and the narrow `drive.file` grant can access the selected parent folder. If no parent folder is configured, Google places the export in the user's My Drive root.

## Slack

The initial Slack adapter deliberately requests only the `incoming-webhook` scope so the installing workspace chooses the destination explicitly and TerraSatch does not receive broad message-history access.

1. Create the TerraSatch Slack app and configure OAuth & Permissions.
2. Add the `incoming-webhook` bot scope.
3. Register the exact redirect URI: `https://api.terrasatch.com/api/v1/workspace/integrations/oauth/slack/callback`.
4. Store the Slack client ID, client secret, and redirect URI in the server-only provider config
   bundle (or the legacy per-provider environment fallback).
5. Distribute or approve the app as required before installing it into customer workspaces.

Slack code exchange uses HTTP Basic authentication for the client credentials. TerraSatch treats the OAuth install as incomplete unless Slack returns the approved incoming webhook destination and channel identifier. Returned bot tokens, refresh tokens when rotation is enabled, and incoming webhook URLs stay inside the encrypted credential payload.

The webhook is bound to the channel selected during Slack authorization; TerraSatch does not override that channel at send time. When token rotation is enabled, TerraSatch refreshes an expired access token before remote revocation so Slack can remove the associated installation and incoming webhook before the local encrypted credential is deleted.

## Esri ArcGIS Online

The first ArcGIS adapter is intentionally read-only and targets ArcGIS Online. TerraSatch uses the
server-side OAuth authorization-code flow and keeps the client secret and refresh token on the API
host. Connected ArcGIS accounts currently expose the provider-neutral `map.features.query`
capability.

Each connection must declare between 1 and 20 approved ArcGIS Online FeatureServer layer URLs.
Satchy can query only those allowlisted layers. Query requests use HTTPS POST, put the OAuth access
token in the HTTP Authorization header, cap a response at 200 features and 2 MB, and reject
non-`*.arcgis.com` destinations. This prevents the layer URL from becoming a general-purpose
server-side request primitive.

ArcGIS Enterprise and feature-editing capabilities remain planned; this adapter does not claim those
capabilities yet.

1. Create ArcGIS OAuth credentials for a server-side application.
2. Register the callback:
   `https://api.terrasatch.com/api/v1/workspace/integrations/oauth/esri_arcgis/callback`.
3. Store the API-only ArcGIS client ID, client secret, and redirect URI in the provider config
   bundle (or the legacy per-provider environment fallback).
4. Create the TerraSatch connection with its approved `feature_layer_urls`.

## Microsoft 365

Microsoft 365 uses delegated Microsoft identity-platform OAuth with `offline_access`, `User.Read`,
and `Files.ReadWrite`. The first supported capability is `document.create`, implemented as a small
file upload to the connected user's OneDrive. Team and organization OneDrive/SharePoint routing is
not advertised yet; the initial connection scope is intentionally personal.

## Snowflake

Snowflake is organization-scoped and uses a customer-created Programmatic Access Token (PAT). The
connection stores only the Snowflake account hostname and optional warehouse/database/schema/role
metadata. The PAT is submitted through the protected credential setup endpoint and encrypted
immediately. The `data.query` capability accepts one read-only `SELECT` statement, rejects
multi-statement/comment syntax, and calls the Snowflake SQL API over the fixed
`*.snowflakecomputing.com` host.

## CalTopo

CalTopo uses its supported Teams service-account API. A team or organization administrator creates a
CalTopo service account, then provides its credential ID and one-time credential secret through the
protected credential setup endpoint. TerraSatch stores the secret only in the encrypted credential
record. Requests use CalTopo's documented HMAC-SHA256 signing flow. The
`map.features.query` capability can read team data or specifically allowlisted map IDs.

## Mapbox

Mapbox is treated as a TerraSatch-managed read service rather than a customer OAuth connection. Its
server-side access token lives only in the provider secret bundle. The current
`map.style.read` capability reads a named style through the fixed Mapbox Styles API host. It does
not grant style-write or token-management permissions.

## Provider access boundaries

Garmin remains marked **partner required** because the Garmin Connect Developer Program requires
business approval before production API access. onX Backcountry, Gaia GPS, and AllTrails remain
**coming soon** rather than pretending unsupported public APIs exist. Their catalog entries remain
visible so customers can see the intended stack without being offered a broken Connect button.

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


## Satchy integration runtime

Provider connections are no longer the interface Satchy needs to reason about. Each provider advertises
generic capabilities such as `document.create` or `notification.send`. When a connection is created,
TerraSatch creates an audience grant for the selected user, team, or organization plus a separate
`agent:satchy` grant for the same supported capabilities.

At execution time the runtime resolves an eligible connected provider from the current user/team/
organization/workflow context and requires both the audience grant and Satchy's agent grant. This keeps
connection ownership, audience permission, and agent authority separate while letting workflows call one
stable interface instead of provider-specific APIs.

The existing provider-specific endpoints remain compatibility/test surfaces. New Satchy workflows should
call the integration runtime by capability.
