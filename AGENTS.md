# AGENTS.md — how to work in this repository

Instructions for any coding agent (Claude Code, Copilot, Cursor…) and for new engineers.
Read this first, then `docs/README.md`.

## What this is
Learning & Knowledge Suite: an LMS (learner, manager, admin) plus a **separate** Knowledge Hub.
Product spec: `docs/prd.md`. Screen IDs (L-01, A-05, K-07…) come from the UI deck and build spec
(sheet 22) and are used in code comments, tests and docs.

## Layout
```
backend/            FastAPI app (Python 3.13, uv). Code only — no tests here.
  app/core/         config, database, security, errors, queue, resilience, health, middleware
  app/shared/       base model mixins, repository, schemas, events, clock, audience
  app/modules/<x>/  one folder per feature: models, schemas, repository?, service, router, rules?, jobs?, subscribers?
  app/seed/         demo company (invented data)
  migrations/       Alembic
frontend/           React + TypeScript + Tailwind v4 (pnpm, Vite)
test/backend/<x>/   backend tests, one folder per feature (pytest)
test/e2e/           end-to-end tests (Playwright)
docs/               PRD, architecture, rules, guides, changelog — keep updated
deploy/             Docker, compose, CI helpers, single-exe build
```

## Commands
| Task | Command (from repo root) |
|---|---|
| Install backend | `uv sync --project backend` |
| Run API | `cd backend && uv run uvicorn app.main:app --reload` |
| Run worker | `cd backend && uv run python -m app.worker` |
| Migrate / seed | `cd backend && uv run python -m app.cli migrate` / `seed` |
| One feature's tests | `uv run --project backend pytest test/backend/<feature>` |
| All backend tests | `uv run --project backend pytest test/backend` |
| Lint / format | `cd backend && uv run ruff check app && uv run ruff format app` |
| New migration | `cd backend && uv run alembic revision --autogenerate -m "what changed"` |
| Frontend dev | `cd frontend && pnpm dev` |
| Frontend checks | `cd frontend && pnpm lint && pnpm build` |
| E2E | `cd test/e2e && pnpm test` |

## Rules that are not optional
1. **Follow the layering**: router → service → (repository/models). Routers hold no business logic; services never import FastAPI. See `docs/backend-code-rules.md`.
2. **Business numbers live in settings** (`app/modules/settings/defaults.py`), never hard-coded (golden rule 8).
3. **Never return a raw 500.** Raise `AppError` subclasses; external services go through circuit breakers with a fallback. See `docs/resilience.md`.
4. **Audit** overrides, exports, deletions, role changes and approvals with `AuditService.record`.
5. **Bulk sends** preview first and support undo for 10 minutes (`BulkActionService`).
6. **Background work** uses `defer_job(...)` (dispatched after commit), never ad-hoc tasks.
7. **UI copy is plain words**, one primary button per screen, no "AI" badges or sparkle icons. See `docs/frontend-ui-guide.md`.
8. **Tests live in `test/`**, never in `backend/`. Add tests for every feature; after a change run that feature's tests; run e2e before pushing.
9. **Docs are part of the change**: update `docs/features.md`, the relevant guide and `docs/changelog.md` in the same change.
10. **Secrets** only in `backend/.env` (gitignored). Never commit keys; `backend/.env.example` lists the variables.
11. Models changed? Add an Alembic migration — `test/backend/core/test_migrations.py` fails on drift.
12. Demo data is invented. Never use real people's data in development or tests.
