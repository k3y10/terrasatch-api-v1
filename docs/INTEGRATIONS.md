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
OAuth credentials are obtained by the API callback. CalTopo service-account credentials, Snowflake
PATs, Microsoft Teams Workflows webhook URLs, and generic webhook secrets are submitted once through
the protected credential setup endpoint for providers that do not offer the same OAuth experience.
All customer secrets are immediately encrypted with Fernet and
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

## Microsoft Teams

Teams notifications use the current Microsoft **Workflows** webhook model, not the retired Microsoft
365/Office 365 connector webhook. In Teams, create a workflow from **Workflows** using the
**When a Teams webhook request is received** trigger (for example, the **Send webhook alerts to a
channel** template), configure the destination channel/chat, and copy the generated HTTPS callback
URL into TerraSatch through the protected credential endpoint as `webhook_url`.

The current TerraSatch adapter supports Workflows configured for callback-URL authorization without
a separate bearer token. The URL is encrypted at rest and never returned after credential submission.
TerraSatch accepts current Microsoft callback hosts under `*.logic.azure.com` and
`*.api.powerplatform.com`, including newer scale-unit callback paths, and sends an Adaptive Card
payload through the provider-neutral `notification.send` capability. The existing human approval,
audience grant, `agent:satchy` grant, and durable idempotency boundary all remain in force.

## Operational email

Operational email is a TerraSatch-managed `notification.send` destination backed by the existing
server-side Resend transport. An administrator creates a team- or organization-scoped connection
with one to ten fixed recipient addresses and a fixed subject. Satchy supplies only the approved
message body at execution time; it cannot choose new recipients, change the sender, or inject a new
subject.

The provider is connectable only when the API/worker has a Resend API key and a verified TerraSatch
sender. `TERRASATCH_INTEGRATION_EMAIL_FROM` is preferred for operational mail; when omitted, the
existing `TERRASATCH_BILLING_FROM` sender is used as a compatibility fallback. Reply-to follows the
same operational-first, billing-fallback pattern. No Resend API key is stored per organization.

Each send uses the durable TerraSatch delivery request ID plus the connection ID as Resend's
`Idempotency-Key`. Resend documents idempotency keys for `POST /emails` with a maximum length of
256 characters and a 24-hour deduplication window. TerraSatch stores only the returned provider
message ID and recipient count in delivery metadata, not recipient addresses.

## Generic HTTPS webhooks

Organization and team administrators can connect an HTTPS webhook as a provider-neutral
`notification.send` destination. The destination URL is treated as a credential and encrypted at
rest; it is never stored in connection configuration. TerraSatch rejects IP-literal, localhost,
`.local`, and `.internal` destinations and never follows redirects.

A generic webhook receives a compact JSON envelope with `type`, `version`, `request_id`, and
`text`. TerraSatch also sends `Idempotency-Key` and `X-TerraSatch-Event` headers. If the
connection is configured with an optional `signing_secret`, TerraSatch adds
`X-TerraSatch-Timestamp` and an HMAC-SHA256 `X-TerraSatch-Signature` over
`<timestamp>.<raw-body>`. Receivers should verify the signature and reject stale timestamps.

## Cloudflare R2

Cloudflare R2 uses its S3-compatible API through the existing provider-neutral `document.create`
capability. Team or organization administrators configure the public R2 S3 endpoint, bucket, and an
optional object prefix. The R2 access key ID and secret access key are submitted once through the
protected credential endpoint and stored only in the encrypted credential record.

TerraSatch signs R2 requests with AWS Signature Version 4 using R2's required `auto` region. Connection
setup performs a signed `HeadBucket` probe, and approved exports use a signed `PutObject` request.
The current adapter accepts only Cloudflare's `*.r2.cloudflarestorage.com` S3 endpoints, keeps
redirects disabled, limits exports to the same approved text/JSON/CSV/Markdown MIME types and 5 MB
boundary used by the document runtime, and never returns R2 credentials to the browser.

Cloudflare recommends creating credentials with Object Read & Write access and scoping them to the
specific bucket TerraSatch should use. R2 jurisdiction-specific endpoints are supported because they
remain under the same Cloudflare R2 S3 hostname suffix.

## Amazon S3

Amazon S3 uses the same provider-neutral `document.create` capability as Drive, OneDrive, and R2.
Team or organization administrators configure a standard AWS Region, bucket, and optional object
prefix. Access key ID and secret access key are stored only in encrypted integration credentials;
temporary credentials may also include an encrypted session token.

TerraSatch uses AWS Signature Version 4 against the standard regional virtual-hosted S3 endpoint
`https://<bucket>.s3.<region>.amazonaws.com`. Connection setup performs `HeadBucket`; approved
exports use `PutObject`. The initial adapter intentionally supports general-purpose regional buckets
only, not S3 Express directory buckets, access-point ARNs, or customer-defined endpoints. Bucket names
are limited to the DNS-safe subset needed for virtual-hosted HTTPS requests.

The adapter keeps the same approved text/JSON/CSV/Markdown MIME types and 5 MB boundary as the
document runtime. For long-lived credentials, use a dedicated least-privilege IAM principal scoped to
the intended bucket/prefix. Temporary STS-style credentials are supported through `session_token`.

## GeoJSON / REST

GeoJSON / REST is a read-only `map.features.query` source for public HTTPS FeatureCollection
endpoints. A team or organization administrator approves exactly one endpoint URL and a maximum
feature count when creating the connection. The URL cannot contain embedded credentials, query
parameters, fragments, IP literals, localhost-style names, or non-HTTPS schemes.

TerraSatch resolves the configured hostname and rejects non-public DNS results at connection setup.
The destination is checked again immediately before a live query, redirects remain disabled, and
the response is streamed with a hard 5 MB ceiling. Returned JSON must be a GeoJSON
`FeatureCollection`; the configured feature limit is between 1 and 1000. If the source contains
more features, TerraSatch returns the configured prefix and marks the response metadata as truncated.

Satchy cannot provide a different URL or runtime filter payload for this provider. The endpoint is
fixed by the administrator, the provider uses no customer credential record, and the normal
organization/team plus `agent:satchy` read grants still apply.

## OGC API Features

OGC API Features is a read-only `map.features.query` integration for standards-based public
feature services. A team or organization administrator configures one public HTTPS API base URL,
between one and 25 approved collection IDs, and a maximum feature count between 1 and 1000.

The initial TerraSatch adapter intentionally implements a narrow Part 1/Core query surface. Runtime
queries may select only an approved collection and may optionally provide a four-value WGS84
`bbox`, an OGC `datetime` instant/interval, and a `limit` no larger than the administrator's
configured maximum. TerraSatch does not expose CQL2 filters, alternate CRS selection, arbitrary
query parameters, writes, or automatic pagination in this first adapter.

The base URL must be public HTTPS without embedded credentials, query parameters, or fragments.
TerraSatch rejects local/IP/internal destinations, checks public DNS during connection setup and
again immediately before live reads, disables redirects, and streams responses through the same
5 MB hard ceiling used by the GeoJSON provider. Responses must be GeoJSON FeatureCollections;
TerraSatch also caps the returned feature list even if a noncompliant service ignores the requested
limit.

The provider uses no customer credential record. Normal team/organization audience grants plus the
`agent:satchy` grant still control access.

## STAC API

STAC API is a read-only `map.features.query` integration for public SpatioTemporal Asset Catalog
services. A team or organization administrator configures one public HTTPS STAC API base URL,
between one and 25 approved collection IDs, and a maximum item count between 1 and 1000.

The first TerraSatch adapter uses the STAC Item Search `/search` endpoint with a deliberately
small query surface: one approved collection, an optional four-value WGS84 `bbox`, optional
STAC/OGC `datetime`, and a bounded `limit`. TerraSatch does not expose free-text search, CQL2
or filter extensions, arbitrary STAC query extensions, asset downloads, writes, or automatic
pagination in this first version.

The base URL must be public HTTPS without embedded credentials, query parameters, or fragments.
TerraSatch rejects local/IP/internal destinations, checks public DNS during connection setup and
again before a live search, disables redirects, and streams responses through a hard 5 MB ceiling.
Search responses must be GeoJSON FeatureCollections whose features contain STAC Item identifiers
and `stac_version`. TerraSatch also caps the returned item list even if a noncompliant service
returns more than the requested limit.

The provider uses no customer credential record. Normal team/organization audience grants plus the
`agent:satchy` grant still control access. Asset metadata can be returned as part of a STAC Item,
but TerraSatch does not fetch or download those assets through this adapter.

## Snowflake

Snowflake is organization-scoped and uses a customer-created Programmatic Access Token (PAT). The
connection stores only the Snowflake account hostname and optional warehouse/database/schema/role
metadata. The PAT is submitted through the protected credential setup endpoint and encrypted
immediately. The `data.query` capability accepts one read-only `SELECT` statement, rejects
multi-statement/comment syntax, and calls the Snowflake SQL API over the fixed
`*.snowflakecomputing.com` host. Snowflake PAT users must also satisfy Snowflake's account
authentication and network-policy requirements.

## CalTopo

CalTopo uses its supported Teams service-account API. A team or organization administrator creates a
CalTopo service account, then provides its credential ID and one-time credential secret through the
protected credential setup endpoint. TerraSatch stores the secret only in the encrypted credential
record. Requests use CalTopo's documented HMAC-SHA256 signing flow. The
`map.features.query` capability can read specifically allowlisted map IDs with READ access. When
no map ID is configured, TerraSatch uses the team account endpoint for discovery, which requires the
CalTopo service account to have ADMIN access.

## Mapbox

Mapbox is treated as a TerraSatch-managed read service rather than a customer OAuth connection. Its
server-side access token, fixed username, and comma-separated approved style IDs live only in the
provider secret bundle. The current `map.style.read` capability can read only those approved styles
through the fixed Mapbox Styles API host. It does not grant style-write, arbitrary private-style
discovery, or token-management permissions.

## Provider access boundaries

Garmin remains marked **partner required** because the Garmin Connect Developer Program requires
business approval before production API access. onX Backcountry, Gaia GPS, and AllTrails remain
**coming soon** rather than pretending unsupported public APIs exist. Their catalog entries remain
visible so customers can see the intended stack without being offered a broken Connect button.

## Lifecycle

OAuth providers use:

`requested -> awaiting_authorization -> connected`

Manual service-account providers use:

`requested -> connected`

after the protected credential setup endpoint validates the supplied credential. A failed provider
exchange, manual credential validation, or connection test moves the record to `error`. A successful provider revocation deletes the encrypted credential and marks the connection `revoked`. OAuth state values are stored only as SHA-256 digests, expire quickly, and are single-use.

Providers without an implemented, documented access path remain `planned` or `partner_required`
instead of being exposed as connectable.

## Supported runtime capabilities

Connected or TerraSatch-managed providers currently expose these server-side capabilities while
keeping customer credentials out of browser state:

- `notification.send`: Slack, Microsoft Teams Workflows, operational email, and generic signed HTTPS webhooks.
- `document.create`: Google Drive, Microsoft OneDrive, Cloudflare R2, and Amazon S3.
- `map.features.query`: approved ArcGIS Online layers, CalTopo Team maps, fixed public GeoJSON feeds, approved OGC API Features collections, and approved STAC collections.
- `data.query`: one read-only Snowflake SELECT statement through the SQL API.
- `map.style.read`: approved TerraSatch-managed Mapbox styles.

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
