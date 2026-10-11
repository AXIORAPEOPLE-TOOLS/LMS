# Testing

## Layout (tests are separate from backend code)
```
test/
  backend/
    pytest.ini         config (pythonpath, asyncio)
    conftest.py        fixtures: database (fresh SQLite per test), client, make_user, inline queue
    testkit.py         helpers: auth(), make_skill/role/course/test builders
    core/              resilience, migrations drift
    identity/  skills/  notifications/  learning/  assessments/  certificates/  pathways/
    gamification/  insights/ (career, home, manager)  reminders/  workflows/  reports/
    knowledge/  seed/ (demo company smoke test across every screen)
  e2e/
    playwright.config.ts   starts its own backend (fresh SQLite + demo company) and the frontend
    start_backend.py       throwaway backend launcher (no Neon/Redis/Groq needed)
    tests/learner.spec.ts  home, pathway, lesson, skill check, boards, career, reminders, certificate verify
    tests/staff.spec.ts    manager team, admin assign+undo, workflows, reports export, monitoring, Knowledge Hub
```

## Commands (repo root)
```bash
uv run --project backend pytest test/backend/<feature>     # after finishing a feature: only its tests
uv run --project backend pytest test/backend               # whole backend suite
TEST_DATABASE_URL=postgresql://…/neondb_test uv run --project backend pytest test/backend   # same tests on Postgres
cd test/e2e && pnpm test                                    # end-to-end, required before pushing
```
Never point `TEST_DATABASE_URL` at a database with real data: tests drop and recreate tables. Use a Neon branch.

## Conventions
- Each feature folder covers: happy path, permissions (who may not), validation/edge cases, and the spec's numbers (e.g. score 68 → level 3, 1,240 points → 260 to Specialist).
- Pure rules get direct unit tests (no database).
- Time-dependent logic freezes the clock: `clock.freeze(datetime(...))`. Tokens use the real wall clock.
- External services are faked at the boundary (queue inline, rules assistant, channel stubs); uploads go to a temporary folder.
- No screenshot/visual tests (by decision); e2e failures keep a Playwright trace instead.
- Query-count checks for list screens when optimising.

## Current status
See `features.md` — each feature lists its test folder. Last full run (2026-10-11): backend **167 passed**, 4 skipped (opt-in live AWS checks, and the Postgres-only test on SQLite); also all passing on PostgreSQL 17. E2E **24 passed** (phone 360 px + desktop).

E2E needs Playwright's browser once: `cd test/e2e && pnpm install && pnpm exec playwright install chromium`.

## CI (`.github/workflows/ci.yml`)
Runs on every push to `main` and every pull request:

| Job | What it checks |
|---|---|
| Secret scan | gitleaks over the full history: no keys or passwords committed |
| Backend | `ruff check`, `ruff format --check`, all backend tests on SQLite (includes the migration drift test), `api.md`/`data-model.md` regenerated and unchanged |
| Backend - PostgreSQL | migrations up → down → up on PostgreSQL 17, then all backend tests on PostgreSQL (production database) |
| Frontend | `pnpm lint`, `tsc` + `vite build`; the build is kept as an artifact |
| End-to-end | Playwright on phone and desktop (own SQLite backend + Vite); report uploaded on failure |

Same checks locally: `bash deploy/ci/check.sh` (add `--e2e` before pushing). Dependabot opens weekly update PRs.

## Live checks against local stand-ins (opt-in)
`docker compose -f deploy/compose.aws-local.yml up -d`, then
`LMS_LIVE_AWS_LOCAL=1 uv run --project backend pytest test/backend/core/test_aws_local_live.py` runs the real SQS and S3
clients against ElasticMQ and S3Mock (skipped otherwise). PostgreSQL: `TEST_DATABASE_URL=postgresql+asyncpg://...`
runs the whole suite there, including the concurrent first-start test.

## Checking each run mode by hand
How to start every mode and the three checks for each (health, a job through the queue, a file upload) are in
`deployment.md` → "How to run each mode, step by step" and "Check that a mode works". Last checked 2026-10-11:
mode 1 deployed (one container), mode 2 deployed (API + worker + Redis) and mode 3 on your machine (ElasticMQ + S3Mock) all passed. Mode 3 on real AWS has not been tried yet.
