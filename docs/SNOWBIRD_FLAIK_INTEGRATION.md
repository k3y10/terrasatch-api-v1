# Snowbird + flaikConnect integration

This integration keeps TerraSatch as the broker between field radio intelligence and Snowbird's existing flaik operational systems.

## Trust boundary

```text
Radio / SDR / reviewed field text
        |
   TerraSatch Edge
        |
        v
api.terrasatch.com
  |- Transmission + Transcript
  |- TerraEngine
  |- OperationalEvent
  `- server-side flaikConnect adapter
          |
          v
     Snowbird flaik environment

Snowbird demo UI
        |
        `----> TerraSatch API only
```

The browser and TerraSatch Edge never receive flaik credentials. Edge remains provider agnostic.

## flaikConnect contract used

The implementation follows flaik's documented server-to-server contract:

- OAuth2 Client Credentials authentication
- environment-specific authentication and API base URLs supplied by flaik
- `GET /health` for connectivity
- `GET /api/globalsettings/resort` for resort settings
- ClassManagement for lesson/class context
- Timekeeping for paid-activity / punch context
- Employees is treated as a capability boundary only; employee records are not returned to the Snowbird demo

Snowbird/flaik-specific ClassManagement and Timekeeping paths must be configured from the authorized Snowbird environment documentation. Do not guess endpoint paths from module names.

## Modes

### disabled

Default. No flaik network calls occur.

```text
TERRASATCH_FLAIK_MODE=disabled
```

### fixture

Safe partner-demo mode with pseudonymous Mountain School records.

```text
TERRASATCH_FLAIK_MODE=fixture
```

### live

Requires server-side credentials and environment URLs supplied by flaik/Snowbird.

```text
TERRASATCH_FLAIK_MODE=live
TERRASATCH_FLAIK_AUTH_URL=https://auth-<region>.<environment>.flaik.com/connect/token
TERRASATCH_FLAIK_API_BASE_URL=https://api-<region>.<environment>.flaik.com
TERRASATCH_FLAIK_CLIENT_ID=<secret>
TERRASATCH_FLAIK_CLIENT_SECRET=<secret>
TERRASATCH_FLAIK_SCOPE=flaik.connect.api.read
TERRASATCH_FLAIK_CLASSES_PATH=<authorized path>
TERRASATCH_FLAIK_TIMEKEEPING_PATH=<authorized path>
```

Use a secret manager or protected deployment environment. Never commit live credentials.

## API resources

```text
GET  /api/v1/integrations/flaik/status
POST /api/v1/integrations/flaik/correlate
```

Both require the tenant-local `read:integrations` service-key scope.

`/status` returns only normalized operational data such as group labels/IDs, participant counts, state, meeting area, time window and aggregate counts.

`/correlate` accepts radio text and an optional callsign, matches it to the normalized flaik class context, then sends that context through the canonical TerraEngine entry point. It does not create a second Snowbird-only intelligence engine.

## PII boundary

Do not expose raw provider employee objects. In particular, the adapter must not return:

- employee or payroll IDs
- employee names
- email addresses
- phone numbers
- postal addresses
- birth dates
- payroll amounts

For live class records the public normalized instructor field indicates assignment only. Demo fixtures use obviously pseudonymous instructor labels.

## Failure behavior

flaik availability is not part of the radio-ingest critical path. A provider timeout or configuration error must not prevent TerraSatch from preserving a radio transmission or generating its normal TerraEngine event.

The Snowbird application may fall back to an explicitly labeled fixture when no TerraSatch service credential is configured. It must never display fixture data as live provider data.
