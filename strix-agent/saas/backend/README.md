# Strix SaaS backend

FastAPI control-plane API for the multi-tenant dashboard. See
`../README.md` and `../TASKS.md` for the overall SaaS build context, and
`../CONFIG.md` for environment variables (mock vs. real GitHub/Stripe/scan
providers).

## Run locally

```
cd saas/backend
uv sync
uv run python -m app.seed        # seeds a demo org + repo (idempotent)
uv run uvicorn app.main:app --reload --port 8000
```

`GET http://localhost:8000/api/health` should return `{"status": "ok"}`.

Data is stored in `saas/backend/strix_saas.db` (SQLite) by default. Delete
that file to reset all local data.

## Schema changes

Schema is managed with [Alembic](https://alembic.sqlalchemy.org/)
(`migrations/`). `app.db.init_db()` (called from the app's lifespan on
every startup) applies any pending migration automatically — there's
nothing to run by hand in normal use. When you add or change a model
field in `app/models.py`, generate the migration for it:

```
uv run alembic revision --autogenerate -m "add foo to bar"
```

Review the generated file under `migrations/versions/` before committing
— autogenerate is a good first draft, not a guarantee (it doesn't detect
every kind of change, e.g. a column rename shows up as a drop + add).

## Tests

```
uv sync --group dev
uv run pytest --cov --cov-report=term-missing
```

125 tests, 100% line coverage (enforced: `fail_under = 95` in
`pyproject.toml`'s `[tool.coverage.report]`). Tests run against an isolated
temp-file SQLite DB (see `tests/conftest.py`) and a real FastAPI lifespan
per test (`TestClient` as a context manager), so the pentest job queue
actually runs — `SAAS_MOCK_SCAN_MIN_SECONDS`/`MAX_SECONDS` are set low in
tests so mock scans complete in ~20ms instead of the production 4-8s.
