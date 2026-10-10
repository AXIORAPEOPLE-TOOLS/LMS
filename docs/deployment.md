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

## Production architecture (decided 2026-10-10): AWS ECS on EC2 + SQS, ap-southeast-1

Chosen for cost: EC2 capacity is cheaper than Fargate per vCPU, and Spot can cover most of the worker load.

```
Users ─► CloudFront ─► S3 (React build)
          └─ /api ─► ALB ─► ECS service "api"     (tasks: 2 → N, target tracking on CPU / ALB requests per target)
                               │ commit → SendMessageBatch
                               ▼
                         SQS: notifications · authoring · reports · scheduled  (+ one dead-letter queue each)
                               │ long-poll (20 s, 10 messages)
                               ▼
                       ECS service "worker"        (tasks: 1 → N, target tracking on backlog per task)
  EventBridge Scheduler ─(every 5 min)─► scheduled queue ("scheduler.tick")

ECS cluster capacity: one Auto Scaling group per capacity provider, managed scaling on
  - "base":  on-demand t4g/m7g (ARM, Graviton), min 1 instance, runs the api base tasks
  - "spot":  Spot m7g/c7g mix, min 0, workers and extra api tasks (interruption = SQS redelivers)
Shared: Neon (pooled URL) · S3 for uploads · Upstash Redis (rate limits, locks) · Secrets Manager ·
        CloudWatch logs/alarms (JSON logs) · SES (email) · WhatsApp Cloud API · Groq
```

| Concern | How it is handled |
|---|---|
| API scale | Stateless containers behind the ALB; ECS adds tasks, the capacity provider adds EC2 instances when tasks do not fit |
| Worker scale | Backlog per task = visible messages ÷ running workers, target ~100; bulk sends add workers within a minute |
| Cost floor | 1 small on-demand Graviton instance + Spot for bursts; workers scale back to 1 task when queues are empty |
| Retries | Message not deleted → reappears after its visibility timeout; growing delay via `ChangeMessageVisibility`; 5 receives → dead-letter queue + alarm |
| Duplicates | SQS is at-least-once; deliveries and helper runs are already idempotent |
| Delays > 15 min | SQS maximum is 15 min; later sends stay in the database and are queued by the 5-minute tick |
| Provider rate limits | Token bucket in Redis (replaces BullMQ's global rate limit) |
| Long jobs | Worker extends the message's visibility while a course draft runs |
| Spot interruption | 2-minute warning → task stops taking messages; in-flight messages reappear and run elsewhere |
| Uploads | Must move from local disk to S3 before running more than one task |

Still to build for this target: `SQSQueue` + SQS worker loop, S3 storage for uploads, Dockerfiles, infrastructure
as code (ECS cluster, capacity providers, ALB, SQS, EventBridge), and the deploy workflow (build → ECR → migrate → ECS rolling update).
