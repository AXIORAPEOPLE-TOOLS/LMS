# Architecture

## Shape: a modular monolith + a worker
```
                 ┌───────────────────────── Browser (React SPA) ─────────────────────────┐
                 │ Learning app (learner/manager/admin)        Knowledge Hub (own nav)  │
                 └───────────────┬──────────────────────────────────────┬────────────┘
                                 │ HTTPS JSON /api/*  (+ SSE for live boards)
                     ┌───────────▼────────────┐        enqueue after commit       ┌───────────────┐
                     │  API (FastAPI, uvicorn) │ ───────────────────────────────▶ │ Redis (Upstash)│
                     │  routers → services     │                                   │  BullMQ queues │
                     └───────┬─────────┬───────┘                                   └───────┬───────┘
                             │         │ assistant calls (circuit breaker)                 │ consume
                             │         └──────────────▶ Groq API ◀── fallback: rules ─┐    │
                     ┌───────▼─────────┐                                               │ ┌──▼─────────────┐
                     │ PostgreSQL (Neon)│ ◀──────────────────────────────────────────── │ Worker          │
                     └─────────────────┘                                               │ jobs + scheduler│
                                                                                       └─────────────────┘
```
- **API** handles requests, writes to Postgres, and *defers* slow work as jobs.
- **Worker** (`python -m app.worker`) consumes queues (`notifications`, `authoring`, `reports`, `scheduled`) and runs the scheduler (daily/weekly tasks).
- **Deployment profiles (`LMS_DEPLOY_PROFILE`)**:
  - `development`: jobs run inline in the API process, local file storage.
  - `single`: worker consumes BullMQ on Redis, local volume file storage.
  - `scalable`: worker long-polls AWS SQS, file storage in S3, EventBridge triggers scheduled ticks, autoscaling on ECS (see `docs/deployment.md`).
- If Redis is down in `single` profile, the API gracefully falls back to running jobs inline.

## Backend layers (per module)
```
router.py      HTTP only: parse input, call one service method, shape output. Auth via dependencies.
service.py     Business logic. Uses repositories/ORM, other services, the event bus, defer_job.
rules.py       Pure functions for the maths in the spec (levels, ranks, readiness, waves, ladder, health).
models.py      SQLAlchemy 2 typed models. No logic beyond small properties.
schemas.py     Pydantic v2 input/output contracts.
jobs.py        @job_handler functions (run by the worker or inline).
subscribers.py event_bus.subscribe(...) reactions to other modules' events.
```
Shared building blocks in `app/core` and `app/shared`:
- `database.py` — engine/session factory, Neon URL normalisation, session-per-request with commit.
- `queue.py` — `defer_job` (outbox-style: dispatched only after commit), BullMQ or inline backend.
- `resilience.py` — `CircuitBreaker` used for Redis, Groq, each notification channel and the database.
- `errors.py` / `middleware.py` — domain errors → friendly JSON; request ids; DB fail-fast.
- `health.py` — component registry → `/api/health` reports `full | limited | offline`.
- `events.py` — in-process domain events (`user.created`, `course.completed`, `skill.level_recorded`…).
- `audience.py` — one "who is this for" model used by assignments, invitations, tests and workflows.

## Modules
| Module | Owns | Publishes | Listens to |
|---|---|---|---|
| identity | users, departments, auth, employee upload | `user.created`, `user.role_changed` | — |
| skills | skills, job roles, role requirements, career moves, levels, ranking | `skill.level_recorded` | — |
| assessments | skill tests, attempts, proctoring, campaigns, in-person bookings | `test.completed`, `certification.passed` | — |
| learning | courses, lessons, quiz, simulations, assignments, sessions, invitations, bulk undo | `lesson.completed`, `course.completed`, `session.created` | — |
| pathways | pathways and items (waves × steps) | `pathway.completed` | `course.completed`, `skill.level_recorded` |
| certificates | certificates, verification, PDF, renewals | `certificate.issued` | `certification.passed` |
| gamification | points, badges, challenges, leaderboards (SSE) | — | lesson/course/test/level/certificate events |
| notifications | in-app inbox, channel delivery | — | — |
| reminders | completion-reminder planning and sending | — | — |
| workflows | definitions, modes, runs, approvals | — | `user.created`, `user.role_changed`, `session.created`, schedule |
| reports | report registry, exports, schedules | — | — |
| home / career / manager / admin_home | read models composing other services | — | — |
| knowledge | Knowledge Hub (separate prefix `/api/knowledge`) | — | — |
| ai | assistant provider interface (Groq / rules) | — | — |
| settings / audit / scheduler | configuration, audit log, scheduled tasks | — | — |
| monitoring | request metrics (per process), system snapshot, live stream | — | — |

The Knowledge Hub depends only on identity, notifications, settings, audit and ai — it works without the learning modules.

## The assistant service (AI behind an interface)
`app/modules/ai/provider.py` defines `AssistantProvider` with four operations: `match_role`, `draft_course`,
`suggest_knowledge`, `answer`. Implementations:
- `RulesProvider` — offline, deterministic (tests, fallback).
- `GroqProvider` — Groq chat completions in JSON mode (`LMS_GROQ_MODEL`, default `openai/gpt-oss-120b`), wrapped in a circuit breaker and falling back to rules on any failure.
Helpers (`app/modules/agents/`) add five operations used step by step: `plan_course`, `write_module`, `draft_quiz`,
`score_written` and `read_request` (see `docs/core-flows.md` A4). Each has a rules version, so nothing depends on Groq.
All outputs are suggestions: course drafts need expert approval; knowledge suggestions are saved only when the person accepts. The UI never labels anything as "AI".

## Key flows
1. **New joiner**: `POST /users` → `user.created` → workflow engine. Mode *hybrid* → one pending batch (preview) → admin approves → assignments, skill checks, welcome.
2. **Skill check → pathway**: attempt submitted → level recorded (`skill.level_recorded`) → points + pathway prove-step check → when all role skills are checked, learner/manager builds waves.
3a. **Helpers**: `POST /admin/helpers/course|quiz` → `agent_runs` row → `agents.run` job (authoring queue) → each step committed so the page shows progress → waits for the expert; `POST /admin/helpers/assign` reads the request at once and waits for HR to confirm.
3. **Course from SOP**: upload → `SourceDocument` → `courses.draft_from_source` job (authoring queue) → assistant draft → notify creator → submit to expert → approve → published.
4. **Mandatory proctored test**: consent → snapshots/flags → submit → flags? `under_review` : finalize → reviewer decision (note required) → certificate via `certification.passed` → appeal to a different reviewer.
5. **Reminders**: `workflows.daily` task → completion-reminders workflow (mode decides) → planned per person inside their window → delivered by job with delay → dropped if the item was finished meanwhile.
6. **Knowledge ladder**: daily task → stages 30/14/7/0 days, weekly while overdue, +14 function head, +30 knowledge admin & excluded from answers, +90 archive suggested → one combined message per person per day.

## Time
Timestamps are stored in UTC. Calendar logic (due dates, "today", quiet hours, streaks) uses the
organisation timezone `LMS_TIMEZONE` (default `Asia/Kolkata`) via `app.shared.clock`.

## Frontend
React 19 + TypeScript + Vite + Tailwind v4, TanStack Query for server state, React Router, Motion for
animation, react-i18next (English/Hindi). Two shells: the Learning app (role-aware navigation) and the
Knowledge Hub (own top bar + app switcher). See `frontend-ui-guide.md`.
