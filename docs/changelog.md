# Changelog

## 2026-10-10 — CI
- GitHub Actions: secret scan, backend lint/tests/docs drift, PostgreSQL migrations + tests, frontend lint/build, Playwright e2e. `deploy/ci/check.sh` runs the same locally. Dependabot for uv, npm and actions.

## 2026-10-10 — Helpers for the HR steps, written answers, API call log
- **Helpers** (Admin → Helpers), one per "AI Agent" process in LMS.pdf, each run showing every step live:
  - *Build a course*: topic, audience, goal, length (+ optional skill, expert, links) → modules with outcomes, content with examples from published company material, links, quick check, own checks and a learner trial → sent to the expert. Nothing is published before approval.
  - *Write a quick check*: ~10 questions (multiple choice + written cases with model answer and rubric), pass mark and time limit, broken/repeated questions removed, saved, tried once → expert approves.
  - *Assign from a request*: "Data privacy basics for Sales by 30 Nov" → course, people and date read, full list shown → HR presses Assign → notices, visibility check, tracker, undo for 10 minutes.
- **Written questions** in course quick checks, scored against a rubric at submit. Unsure scores (setting `learning.written_review_below`) are held and checked by the course expert or an admin on **Answers to check**; the learner is told when the result is final.
- New settings: `learning.written_review_below`, `learning.quiz_default_size`, `learning.quiz_written_count`, `learning.quiz_minutes_per_question`, `learning.default_due_days`, `learning.helper_use_knowledge`.
- Course page: "Write the quick check" button; written questions show their rubric.
- **API call log**: one line per call with status, time, user id and request id; slow calls (`LMS_SLOW_REQUEST_MS`) and errors flagged; secrets in query strings masked; uvicorn's duplicate access line silenced (`LMS_LOG_REQUESTS`).
- Migration `f3d9b6a2c4e8` (agent_runs; question kind/model answer/rubric; attempt written marks and review; course quiz time limit).

## 2026-10-10 — Queue: heavy load and retries
- Bulk enqueue: jobs go to Redis in batches (`addBulk`, 200 per round trip) instead of one round trip each (≈0.5 s to Upstash), so big assignments return in seconds.
- Idempotent jobs (`jobId = name:id:attempt`); delivery locks the notification row and skips channels already done, so retries never send twice or log twice.
- Channel retries: a failed email/WhatsApp is retried 3 more times with growing delays; the message log shows "Retry 2 in 5 s" / "No more retries".
- Redis down: requests still succeed; at most 50 deliveries run inline, the rest are picked up by the new hourly `notifications.redeliver` sweep.
- Worker: concurrency, retries, backoff and a global delivery rate limit are configurable (`LMS_WORKER_CONCURRENCY`, `LMS_JOB_ATTEMPTS`, `LMS_JOB_BACKOFF_MS`, `LMS_NOTIFICATION_RATE_PER_SECOND`, …). Heartbeat now shows the backlog per queue and the retry plan when a job fails.
- `docs/resilience.md`: new section "Background jobs under load, and retries".

## 2026-10-10 — Automation runs end to end (email/WhatsApp simulated)
- Due-date reminders at 7 days, 2 days and on the due date (setting `reminders.due_stages_days`), once per stage, inside the person's best time; dropped at delivery if the training is finished.
- The day after a deadline each manager gets one list of their overdue people.
- After a test the person gets their result and what to do next (tries left); every morning managers get their team's results and HR admins get everyone's.
- Three new default workflows (auto): Due-date reminders, Overdue list after the deadline, Results summary for HR and managers (10 in total).
- Message log: `delivery_logs` keeps one row per message per channel (to, subject, full text with link, status, reason). Email and WhatsApp are **simulated** (status "Simulated", nothing leaves the system) until a provider is connected; in-app is real. Admin page **Message log** with filters, today's counts and "Run today's automations now".
- Users have an optional phone number (My reminders) for WhatsApp; demo people get invented numbers. `LMS_PUBLIC_APP_URL` builds full links in messages. Migration `e7c1a9d3b5f2`.
- Spec PDFs added to `docs/` (`LMS.pdf`, `LMS_Build_Spec.pdf` cover sheet).

## 2026-10-10 — Core flows first
- New `docs/core-flows.md`: learning loop + knowledge loop diagrams, data model (MVP vs later), permissions matrix, MVP/V2/V3, acceptance tests. PRD now points to it as the priority.
- Sign-up: employees create an account and pick their job role (`POST /auth/signup`, public `GET /auth/signup-options`); settings `identity.allow_self_signup` and `identity.signup_email_domains`. Audited.
- Profile and home show **Skills for my role** with separate states: needed by the role, training (none · assigned · in progress · course done) and level proven by a test. Finishing a course never changes a level.
- Assign training is a page (`/admin/assign`): pick a skill → course → "everyone whose role needs this skill" and/or people by name (search, filter by role and department) → due date → full list preview with "has it" marks → send. Audience gains `skill_id`; choices add up.
- Every course-test attempt is stored (`course_quiz_attempts`: answers, score, pass, attempt number; migration `d4b8e2f7a610`). Learners can list their tries.
- Training tracker (`/admin/training`, managers see their team): per course counts and per person state, lessons, best score, tries, due/overdue; CSV export (audited).
- Landing page at `/`; signed-in home moved to `/home`. New login and sign-up pages sharing one layout.
- Learn has three tabs: To do (courses, tests, live classes together), Browse courses, Done (with certificates).
- My path is "My learning plan": stages, a numbered 4-step tracker per skill in plain words, later stages show what is in them and when they start.
- Plain words everywhere: Test (was skill check), Live class (was live session), Stage (was wave), Must do (was mandatory).
- Long lists beside shorter columns scroll inside their card (`scroll-panel`).

## 2026-10-10 — UI pass: one top navigation, lighter look
- Navigation: a single top bar on every screen (sidebar and bottom tab bar removed). Knowledge, My team and Admin are menus in that same bar; the separate Knowledge Hub shell and the app switcher are gone, so opening Knowledge no longer changes the navigation. Phones get a menu button.
- Knowledge Hub is for records staff only: admin, knowledge_admin, function_head, manager, plus anyone who owns, backs up or heads part of the Hub. Enforced on every `/api/knowledge` route (403 for plain learners); `/me` returns `can_open_knowledge` so the UI hides the menu and routes.
- Course quick check: correct answers and reasons are only sent after a pass (they were readable in the network response before). Tries are limited by the new setting `learning.quiz_max_attempts` (default 3, 0 = no limit); pass mark default moved to the setting `learning.quiz_pass_mark` (was hard-coded). New column `assignments.quiz_attempts` (migration `c2a7d4e91f03`).
- Layout: Learn tabs (my learning, skill checks, sessions), certificates, admin sessions and a team member's pathway are card grids; approvals and messages use the page width.
- Knowledge home: the right column now holds My items, Must know and Recently verified; open menus mark the current page.
- Worker logging: timestamps, start/done/failed line per job with timing, a heartbeat every 60 s (jobs done/failed, last job) and a line for every scheduler tick, so a quiet worker is visibly alive.
- Colour: lighter greens and a soft gradient (page background and next-step panels) in two colours only, green and gold.
- Splash: plain centred product name on a light background (≤ 1 s).
- Layout: full-width pages; Home is a two-column dashboard (next step + pathway beside coming up).
- Course quick check: the result shows the score, "x of y right" and the pass mark, with a direct "Restart quiz" button. Correct answers are no longer shown next to the retry.

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
