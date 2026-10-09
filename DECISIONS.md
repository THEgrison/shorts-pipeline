# Architecture decisions

Log of non-obvious choices. Prefer the simplest option when ambiguous.

## 2026-10-09 — Phase 1

### Package manager: `uv` (not Poetry)
Faster installs, lockfile, and first-class Docker support via official images.

### Python 3.12 in Docker / CI, requires-python `>=3.11`
Matches the cloud agent runtime (3.12) while keeping the floor at 3.11 as specified.

### Enums stored as VARCHAR (`native_enum=False`)
Avoids PostgreSQL ENUM migration pain; values validated in Python via `StrEnum`.

### Sync + async SQLAlchemy URLs
FastAPI uses async (`asyncpg`); Celery workers and Alembic use sync (`psycopg2`) to keep worker code simpler.

### Local `StorageBackend` only for now
Interface is ready for S3/MinIO; no cloud dependency until needed.

### API port `8742`
Uncommon port to reduce collisions with default 3000/8080 services.

### Dashboard: minimal HTML first, HTMX/React in Phase 7
Phase 1 only needs health/metrics and a placeholder home page.

### Fernet key fallback
If `FERNET_KEY` is not a valid Fernet key, derive one from `SECRET_KEY` and log a warning — unblocks local/dev without blocking on key format.

### Docker optional in this cloud environment
Compose files are first-class; local unit tests use SQLite in-memory so CI/agent runs without Docker.
