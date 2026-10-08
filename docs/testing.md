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
See `features.md` — each feature lists its test folder. Last full run: backend **111 passed**, e2e **22 passed** (phone 360 px + desktop).

E2E needs Playwright's browser once: `cd test/e2e && pnpm install && pnpm exec playwright install chromium`.
