# Changelog

## 2026-10-09 — Frontend, monitoring, end-to-end tests
- React frontend (Vite 8, React 19, Tailwind 4, TanStack Query, React Router 8, Motion, Radix, Recharts, i18next): every screen from the UI deck — learner (L-01…L-10), manager (M-01…03), admin (A-01…A-09, settings), Knowledge Hub as a separate app (K-01…K-13).
- Design system from the deck (forest/gold, Source Serif 4 + Source Sans 3), splash screen, page transitions, staggered lists, count-ups, reduced-motion support; no "AI" labels or icons anywhere.
- Persisted query cache + limited-mode banner: the UI keeps showing the last data when the backend is degraded.
- Admin monitoring page ("Everything, live"): server gauges, API load sparklines, busiest routes, database, Redis/BullMQ queues, circuit breakers (manual reset), scheduled tasks, workflow runs, recent errors — streamed over SSE.
- Backend: request metrics collector, `/api/admin/monitoring` (+ stream), `/people` directory, learner quiz endpoint `/courses/{id}/quiz`.
- Robustness fix: a database endpoint that cannot be reached (e.g. deleted Neon endpoint, auth failure) now returns a calm 503 and trips the breaker instead of a 500.
- Database moved to Neon `ap-southeast-1` (≈3× lower latency from India). Startup on Postgres runs Alembic migrations; `app.cli migrate` adopts a schema created without migration history.
- Playwright e2e suite (phone 360 px + desktop): 22 passing. Backend: 111 passing.
- Test isolation: backend tests write uploads to a temporary folder; `uploads/` is gitignored everywhere (knowledge files and proctoring pictures never enter the repo). Screenshot tests removed from e2e.
- Repo: root `README.md`, editor config (`pyrefly.toml`, `.vscode/settings.json`) so type checking uses the backend venv.

## 2026-10-09 — Backend foundation and all feature modules
- FastAPI backend (Python 3.13, uv): core config, database (Neon-ready URL handling, PgBouncer-safe prepared statements), security (Argon2 + JWT), domain errors, structured logging.
- Resilience layer: circuit breakers for database, Redis, Groq and each notification channel; friendly error contract with request ids; `/api/health` with full/limited/offline modes.
- Queue: BullMQ on Upstash Redis with outbox-style dispatch after commit; inline fallback; worker process with scheduler and Redis lock.
- Assistant service: provider interface, Groq (gpt-oss-120b, JSON mode) with automatic rules fallback.
- Modules: identity (+ employee upload with role matching), skills (levels, ranking, readiness), assessments (skill checks, proctoring, review, appeals, campaigns), learning (courses, lessons, quiz, simulations, assignments with undo, course builder, sessions & invitations), pathways, certificates (PDF + QR + verify + renewals), gamification (points, badges, streaks, challenges, live boards), career map, learner home, manager team view, admin home, reminders engine, workflows engine (7 ready-made workflows), reports centre (15 reports, exports, schedules), Knowledge Hub (items, versions, revisions, reviews, access, lists, categories, ladder, dashboards, search/ask), settings, audit, scheduler.
- Organisation timezone (`LMS_TIMEZONE`) for calendar logic.
- Alembic initial migration (50 tables) applied to Neon; demo company seeded.
- Tests in `test/backend/` per feature: 106 passing. Docs folder created.
