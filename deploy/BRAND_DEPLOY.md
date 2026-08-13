# Brand-only API landing deployment

The public `https://www.terrasatch.com` site is the visual source of truth for the API root. This change aligns the API landing page to the current TerraSatch field-intelligence identity while keeping the API host lightweight and operator/developer focused.

This branch changes the public landing page, landing-page tests, brand-asset coverage, and this deployment note. It does not add a database migration.

After merge to `main`, update Oracle with:

```bash
cd /opt/terrasatch/api
git status -sb
git checkout main
git pull --ff-only origin main

docker compose config >/dev/null
docker compose build api worker
docker compose up -d --force-recreate api worker

docker compose ps
curl --fail http://127.0.0.1:8000/health/ready
curl --fail https://api.terrasatch.com/health/ready
```

Then visually verify:

- `https://api.terrasatch.com/`
- `https://api.terrasatch.com/docs`
- `https://api.terrasatch.com/openapi.json`
- `https://api.terrasatch.com/admin`

No Alembic command is required for this change.
