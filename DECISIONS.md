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

## 2026-10-09 — Phase 2

### Dummy agents before real integrations
Orchestrator + Celery wiring is validated with `Dummy*Agent` implementations that persist real DB rows. Real YouTube/Whisper/LLM clients arrive in phases 3–6 without changing the orchestrator contract.

### Pause flags: Redis with in-process fallback
Agent pause uses Redis keys when available; falls back to a process-local set so unit tests and Redis-less smoke runs still work.

### `require_review` gates publishing
Default `REQUIRE_REVIEW=true`: after render, clips enter `awaiting_review` until `/api/pipeline/clips/{id}/approve`.

## 2026-10-09 — Phase 3

### Discovery falls back to DummyAgent without `YOUTUBE_API_KEY`
Keeps local/CI runnable; production sets the key and gets the real agent automatically.

### CC-first search + optional whitelist search
Always query `videoLicense=creativeCommon` first (cheaper authorization). General search only runs when a whitelist is non-empty, to find owned-channel videos.

### Scoring weights (simple, tunable later)
Views 25 / like-ratio 20 / velocity 20 / freshness 15 / duration 15 / language 5 = 100.

## 2026-10-09 — Phase 4–5

### Analysis collaborators are injectable
Downloader / Transcriber / MomentDetector interfaces allow Fake* doubles in tests while production uses yt-dlp, faster-whisper, Claude.

### Editing falls back to Dummy when media is invalid
Orchestrator probes with ffprobe before invoking ffmpeg so placeholder analysis files do not crash the pipeline in tests/dry-run.

## 2026-10-09 — Phase 6–8

### Publishing defaults to private / SELF_ONLY
Safer for unaudited TikTok apps and accidental live posts; flip per-request when ready.

### Instagram needs a public `video_url`
Graph Reels API does not accept raw local uploads in this implementation; dry-run works; production should point to CDN/S3 URL.

### Dashboard is HTMX + Jinja (not React)
Fastest path to a usable control plane; React can replace later without changing API routes.

### Scheduler slots interpreted as UTC
Keep timezone logic simple; store IANA tz in `schedule_config` for a future upgrade.
