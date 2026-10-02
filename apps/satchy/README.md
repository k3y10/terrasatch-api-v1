# Satchy frontend

Standalone Satchy-first browser application for `satchy.terrasatch.com`.

## Architecture

This frontend does not maintain a separate identity store. It uses the canonical
`@terrasatch/sdk` package from this repository and talks directly to
`https://api.terrasatch.com` with credentialed browser requests.

The TerraSatch API owns:

- authentication and the signed session cookie;
- users, organizations, roles, and membership;
- CSRF enforcement;
- Workspace context;
- Satchy chat, runs, and action review;
- integrations, field records, and Edge data.

The session cookie remains host-scoped to `api.terrasatch.com`.

## Local development

Copy `.env.example` to `.env.local`, then run:

```bash
npm install
npm run dev
```

Local development requires the local origin to be allowed by the target API CORS
configuration. Production is explicitly configured for
`https://satchy.terrasatch.com`.

## Vercel

Create a dedicated Vercel project from this repository with:

- Root Directory: `apps/satchy`
- Framework: Next.js
- Production environment:
  `NEXT_PUBLIC_TERRASATCH_API_ORIGIN=https://api.terrasatch.com`
- Production domain: `satchy.terrasatch.com`

No TerraSatch password, API secret, database credential, or signing secret belongs
in Vercel for this browser application.
