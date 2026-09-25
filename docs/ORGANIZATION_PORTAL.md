# TerraSatch Organization Portal

The organization portal gives each human user an individual browser login while preserving the existing TerraSatch superadmin console.

## Browser surfaces

- `/admin` — TerraSatch superadmin operations console configured from deployment secrets.
- `/admin/members` — superadmin member creation, password reset, and organization-role assignment.
- `/portal` — organization-scoped member portal.
- `/portal/fleet-status` — session-protected fleet JSON for the organization portal and public radio console.

## Identity model

Human access uses the existing `User` and `Membership` records. A user may belong to more than one organization. Each membership stores one of the existing roles:

- `owner`
- `admin`
- `operator`
- `viewer`

The user record now has an optional scrypt password hash for local browser authentication. Existing users remain valid after migration because the new field is nullable until a superadmin assigns a password.

## Current authorization boundary

All member roles are restricted to organizations where an enabled membership exists. Edge access follows the existing role hierarchy:

- `viewer` — read-only organization and fleet summary.
- `operator` — viewer access plus organization-scoped Edge diagnostics: runtime version/platform, heartbeat state, hardware inventory, capabilities, telemetry, effective remote policy, and Satchy channel binding.
- `admin` / `owner` — operator access plus bounded Edge lifecycle management: rename the device, change its assigned site, and enable/disable the registered Edge.
- TerraSatch superadmin — global/root operations across organizations, API keys, pairing administration, radio policy, and other platform controls.

Portal Edge management deliberately does not grant RF transmit authority. TX remains hardware/provider-capability gated, policy gated, and operator/human-approval controlled. Pairing approval remains in the superadmin flow until portal-user approval can be recorded with complete audit attribution.

## Multiple devices

Fleet responses aggregate:

- total registered devices
- online / stale / offline / never / disabled health
- distinct site count
- RX-capable device count
- TX-capable provider count
- devices needing attention

Each device retains its full hardware inventory in the backend, but operator-facing UI selects a primary radio/receiver device first. This prevents host Bluetooth, webcam, Ethernet, WARP, and other unrelated interfaces from overwhelming the radio health card.

## Multiple organizations

A member with access to several organizations can switch organizations in `/portal`. The chosen organization is remembered in the browser session. When that member returns to the TerraListen radio console, the live fleet card uses the remembered tenant context.

A TerraSatch superadmin session continues to see the global fleet across all organizations unless an organization is explicitly selected in Admin.

## Password handling

Passwords are never stored in plaintext. `/admin/members` hashes submitted passwords with the same fixed-cost scrypt implementation used for the bootstrap administrator. A superadmin can reset an existing user's password by submitting the same email again.

Use HTTPS in production and share temporary credentials out-of-band.

## Beta workspace overview

The connected customer portal displays organization-scoped subscription limits, API entitlement, device reporting state, and administrator permissions. Restricted or unknown managed billing state takes precedence over plan inclusion. Pilot access without self-service entitlements is labeled for administrator confirmation. Limits are not remaining usage, device reporting does not assert every capability is enabled, and development cards do not grant access. Refresh the dashboard after changing billing or device configuration.
