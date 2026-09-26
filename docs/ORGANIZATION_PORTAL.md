# TerraSatch Organization Portal

The organization portal and superadmin console share one database-backed human identity. A user can sign in once and access every authorized surface.

## Browser surfaces

- `/admin` — TerraSatch superadmin operations console for users with the platform `is_superadmin` capability.
- `/admin/members` — superadmin member creation, password reset, and organization-role assignment.
- `/portal` — organization-scoped member portal.
- `/portal/fleet-status` — session-protected fleet JSON for the organization portal and public radio console.

## Identity model

Human access uses the existing `User` and `Membership` records. A user may belong to more than one organization. Each membership stores one of the existing roles:

- `owner`
- `admin`
- `operator`
- `viewer`

The user record stores the scrypt password hash used by both `/portal` and `/admin`, plus `is_superadmin` for platform-wide administration. Organization authority remains separate in `Membership.role`; TerraSatch founders can therefore be both platform superadmins and organization owners without maintaining a second login.

## Current authorization boundary

The portal is intentionally observation-first. All member roles are restricted to organizations where an enabled membership exists. The current portal exposes fleet health, sites, primary radio hardware, RX/TX capability state, and listening health. It does not expose the superadmin command terminal or destructive controls.

The persisted role is available for future per-action authorization when customer write workflows are enabled. Until then, high-risk configuration and tenant administration remain in the superadmin console.

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

## Unified founder / superadmin identity

A database-backed superadmin uses the same signed browser session across `/portal`, `/portal/email`, and `/admin`. Logging into the portal as a superadmin unlocks the admin console; logging into the admin console establishes the portal identity as well.

The deployment setting `TERRASATCH_ADMIN_SESSION_SECRET` remains required because it signs browser sessions. `TERRASATCH_ADMIN_EMAIL` and `TERRASATCH_ADMIN_PASSWORD_HASH` are retained only as legacy bootstrap / break-glass credentials while older deployments migrate.

Use the one-time migration command to copy the existing legacy admin password hash into a canonical User without revealing or retyping the password:

```bash
terrasatch admin migrate-identity \
  --email keaton@terrasatch.com \
  --display-name Keaton \
  --organization <organization-id-or-slug>
```

The migrated user is enabled, marked `is_superadmin=true`, and assigned the selected organization's `owner` role.

## Password handling

Passwords are never stored in plaintext. `/admin/members` and the unified identity use the same fixed-cost scrypt representation. Password reset increments the user's credential version and therefore remains the canonical way to replace the credential after migration.

Use HTTPS in production and share temporary credentials out-of-band.
