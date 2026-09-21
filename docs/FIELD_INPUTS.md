# Field Inputs

TerraSatch treats radios, Garmin inReach, and mobile clients as source adapters into one canonical
operational pipeline. They do not get separate intelligence models.

```text
Radio / Edge ─────────┐
Garmin inReach ───────┼─→ Transmission → Transcript → TerraEngine → OperationalEvent
TerraSatch Mobile ────┘
```

## Garmin inReach Portal Connect

The prepared Garmin receiver is:

`POST /api/v1/field/garmin/inreach/{connection_id}`

It is intentionally receive-only in this first field-input batch. Garmin IPC Outbound pushes one or
more events to the endpoint. TerraSatch accepts schema versions 2.0, 3.0, and 4.0, including free
text, location, transport mode, status, and v4 media metadata/transcription.

A Garmin connection fixes the TerraSatch site and may optionally fix an agent/channel plus an IMEI
allowlist. The IPC static token is kept in TerraSatch's encrypted integration credential record.
The receiver accepts either `Authorization: Bearer <token>`, a raw `Authorization` token, or
`X-Garmin-Token`; actual production header configuration must be verified against the approved
Garmin Portal Connect tenant before the provider is marked supported.

Garmin retries failed HTTP deliveries, so TerraSatch derives a deterministic source message ID from
the provider event. A repeated Garmin delivery returns the existing canonical transmission instead
of creating a duplicate.

Garmin source position is preserved in `rf_metadata.garmin` and applied to generated operational
events when TerraEngine does not already provide a location. Large v4 `mediaBytes` and generic
binary payloads are not copied into transmission metadata; only safe metadata such as media ID,
type, encoded size, and transcription presence is retained.

The public provider catalog remains `partner_required` until Garmin access is approved and live IPC
acceptance testing is possible.

## TerraSatch Mobile

Authenticated workspace members with operator-or-higher access can submit native field observations
through:

`POST /api/v1/workspace/organizations/{organization_id}/field/observations`

The request supports:

- text notes;
- voice transcripts produced by the mobile client;
- photo-note records;
- GPS latitude/longitude, altitude, and accuracy;
- capture timestamps;
- client-generated idempotency IDs;
- media reference IDs.

The mobile endpoint derives organization and user identity from the existing workspace session,
requires CSRF protection, and passes the observation through the same canonical ingest service as
radio and Garmin. GPS is preserved as source provenance and applied to operational events when
needed.

Binary photo/audio upload and offline store-and-forward are separate mobile transport/storage
features. This contract deliberately keeps media references in the observation record so those
features can be added without changing the canonical field-ingest model.
