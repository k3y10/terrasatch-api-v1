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

## Password handling

Passwords are never stored in plaintext. `/admin/members` hashes submitted passwords with the same fixed-cost scrypt implementation used for the bootstrap administrator. A superadmin can reset an existing user's password by submitting the same email again.

Use HTTPS in production and share temporary credentials out-of-band.
