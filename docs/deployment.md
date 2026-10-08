# Deployment

## Environments
| Env | Database | Queue | Assistant | Notes |
|---|---|---|---|---|
| Local dev | Neon (shared dev branch) or SQLite (`sqlite+aiosqlite:///./lms-dev.db`) | `inline` or Upstash | `rules` or `groq` | tables auto-created in non-production |
| Test (CI) | SQLite per test (or `TEST_DATABASE_URL` Neon branch) | inline | rules | |
| Production | Neon (pooled URL) | Upstash Redis + BullMQ | groq | migrations via `app.cli migrate` |

## Configuration (environment variables, prefix `LMS_`)
| Variable | Example | Purpose |
|---|---|---|
| `LMS_ENVIRONMENT` | `production` | `development` auto-creates tables; `production` expects migrations |
| `LMS_DATABASE_URL` | `postgresql://…-pooler…/neondb?sslmode=require&channel_binding=require` | Neon URL pasted as-is (handled in `database.py`) |
| `LMS_JWT_SECRET` | 64 random chars | token signing (`openssl rand -hex 32`) |
| `LMS_CORS_ORIGINS` | `https://lms.yourcompany.com` | comma separated |
| `LMS_TIMEZONE` | `Asia/Kolkata` | calendar days, quiet hours |
| `LMS_REDIS_URL` | `rediss://default:<token>@<host>.upstash.io:6379` | BullMQ (TCP, TLS) |
| `LMS_QUEUE_BACKEND` | `bullmq` | `inline` runs jobs in the API process |
| `LMS_AI_PROVIDER` / `LMS_GROQ_API_KEY` / `LMS_GROQ_MODEL` | `groq` / `gsk_…` / `openai/gpt-oss-120b` | assistant service |
| `LMS_SCHEDULER_ENABLED` | `false` on API, scheduler runs in the worker | |
| `LMS_SEED_DEMO_DATA` | `false` in production | |
| `LMS_FRONTEND_DIST_DIR` | `/app/web` | serve the built SPA from the API (single container / exe) |
| `LMS_UPLOAD_DIR` | `/data/uploads` | knowledge files, proctoring snapshots (mount a volume / use object storage later) |

## Latency: put the API next to the database
The database is Neon **ap-southeast-1 (Singapore)**. From India one SQL round trip is ~90 ms (it was
~300 ms on us-east-2); a home screen makes ~10–17 queries. Deploy the API and worker **in the same
region as Neon** (AWS ap-southeast-1) so round trips are ~1 ms. For fast local development you can use
a local SQLite URL (`sqlite+aiosqlite:///./lms-dev.db`).

## Schema
- Postgres (any environment): the API runs Alembic migrations on startup; production should run
  `python -m app.cli migrate` as a release step instead.
- `migrate` adopts a database whose tables exist but has no migration history (stamps it, then upgrades).
- SQLite (tests, e2e) uses `create_all`.

## Release steps (manual, until CD is added)
```bash
cd backend
uv sync --frozen
uv run python -m app.cli migrate          # schema
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
uv run python -m app.worker               # separate process: queues + scheduler
cd ../frontend && pnpm install --frozen-lockfile && pnpm build   # static files in frontend/dist
```
Docker images, compose, CI/CD and the single-exe build are added in the delivery phase (see `features.md`).
