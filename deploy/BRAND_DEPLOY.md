# Brand-only API landing deployment

This branch changes only the public landing page, landing-page tests, and brand-alignment documentation. It does not add a database migration.

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
