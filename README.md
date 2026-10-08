# Learning & Knowledge Suite

An LMS (learner, manager, admin) plus a separate **Knowledge Hub**, built from the UI deck and build
specification. FastAPI + PostgreSQL (Neon) + Redis/BullMQ (Upstash) on the backend; React + Tailwind on
the frontend.

## Quick start
```bash
# backend (needs backend/.env — copy backend/.env.example)
cd backend && uv sync && uv run uvicorn app.main:app --reload      # http://localhost:8000/api/docs
uv run python -m app.worker                                         # queues + scheduler (optional with LMS_QUEUE_BACKEND=inline)

# frontend
cd frontend && pnpm install && pnpm dev                             # http://localhost:5173
```
Demo sign-ins (password `Demo@1234`): `asha@example.com` (learner), `manager@example.com`,
`admin@example.com`, `meera@example.com` (knowledge owner).

## Tests
```bash
uv run --project backend pytest test/backend          # backend (per feature: test/backend/<feature>)
cd test/e2e && pnpm install && pnpm test               # end-to-end — run before every push
```

## Docs
Start with [`AGENTS.md`](AGENTS.md) and [`docs/README.md`](docs/README.md): PRD, architecture, feature
tracker, backend code rules, frontend UI guide, resilience, testing and deployment.
