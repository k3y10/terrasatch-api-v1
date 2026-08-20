# TerraSatch Partner Identity and Integration Model

This increment extends the Phase 1 control plane for many organizations and their employees without
creating UAC-, Snowbird-, or Flaik-specific authorization silos.

## Authorization hierarchy

```text
Account
  -> Organization
      -> Membership (owner/admin/operator/viewer)
      -> Sites
      -> Teams
          -> TeamMembership (explicit human access)
```

A single `User` is globally unique by email and may hold independent memberships in multiple
organizations. Organization membership is the hard tenant boundary. Team membership narrows the
operating view inside that organization; it never grants access across organizations.

Examples:

```text
Utah Avalanche Center
  -> Forecasting
  -> Field Team
  -> Operations

Snowbird
  -> Patrol
  -> Mountain School
  -> Operations
```

The same human may belong to more than one team, and may separately belong to more than one
organization. Roles and team membership are intentionally separate.

## Partner application context

`/portal/context` returns the signed-in human's selected organization, role, enabled sites, and
enabled teams with an `assigned` flag. It is the canonical browser-session context for partner UI
development.

The current portal cookie remains scoped to `api.terrasatch.com`; a separate Vercel application
must not copy or synthesize that session. A future SSO/token-exchange layer can consume the same
organization/team model without changing the database relationships.

Service integrations can manage explicit team assignment through:

```text
GET /api/v1/team-memberships/{user_id}
PUT /api/v1/team-memberships/{user_id}
```

The API derives `organization_id` from the service credential. A caller cannot supply an arbitrary
organization in the request.

## Provider integrations

Phase 1 already introduced tenant-owned `DataSource` and `SourceConnection` records. Partner
provider configuration resolves through those records:

```text
Organization
  -> Site
      -> DataSource(provider="flaik", adapter_key="flaik_context")
          -> SourceConnection
              endpoint_url
              credential_reference
```

Provider credentials are never stored in `DataSource.configuration`. The first executable secret
reference form is:

```text
env://SNOWBIRD_FLAIK_CLIENT_SECRET
```

Each organization/site may point to a different environment variable or later secret-manager
reference. This avoids process-global Snowbird credentials becoming the architecture for every
future partner.

## Snowbird / flaik

The Flaik endpoint is organization-scoped by the authenticated TerraSatch service key and
optionally site-scoped:

```text
GET  /api/v1/integrations/flaik/status?site_id=<snowbird-site-id>
POST /api/v1/integrations/flaik/correlate
```

`DataSource.configuration` may contain only non-secret fields such as:

```json
{
  "mode": "fixture",
  "resort_name": "Snowbird",
  "auth_url": "https://authorized-auth-host/connect/token",
  "client_id": "server-side-client-id",
  "scope": "flaik.connect.api.read",
  "classes_path": "/authorized/class/path",
  "timekeeping_path": "/authorized/timekeeping/path",
  "timeout_seconds": 8
}
```

Live credentials remain in the referenced secret. The API normalizes operational group data and
never returns raw employee/provider objects.

Flaik classes such as `MS-204` are operational context, not TerraSatch Teams. A persistent
TerraSatch `Mountain School` team can own authorization while a changing Flaik class ID stays inside
the event's `operational_context`.

## Deliberately deferred

This branch does not deploy or migrate production. Before production use:

1. Run the full local API test/coverage gate.
2. Apply `0007` then `0008` to an isolated staging database.
3. Create test organizations for UAC and Snowbird with separate users and team memberships.
4. Verify cross-organization negative cases.
5. Configure a Snowbird Flaik `DataSource` in fixture mode, then a credential-referenced staging
   source if authorized provider credentials are available.
6. Wire team attribution into canonical radio `Transmission` and `OperationalEvent` persistence
   after the identity boundary is validated.
7. Add the SSO/token exchange needed for separate partner web applications; do not share browser
   cookies across unrelated origins.

The canonical radio path remains `Transmission -> Transcript -> TerraEngine -> OperationalEvent`.
No second partner-specific event architecture is introduced.
