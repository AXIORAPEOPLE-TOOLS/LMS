# Feature tracker

Legend: ✅ done · 🟡 partial · ⬜ not started. "Tests" = folder under `test/backend/` (and `test/e2e/` for UI).
Update this table in the same change as the code.

## Platform
| Feature | Backend | Frontend | Tests | Notes |
|---|---|---|---|---|
| Sign-in (email + password, JWT), profile, preferences | ✅ | ✅ | identity | SSO later |
| Roles & permissions (learner, manager, admin, knowledge_admin, function_head, expert, reviewer) | ✅ | ✅ | identity, knowledge | |
| Settings table (golden rule 8) | ✅ | ✅ | reminders, notifications | `/api/settings` |
| Audit log | ✅ | ✅ | identity, assessments, reports | |
| Resilience: breakers, friendly errors, health modes | ✅ | ✅ | core | `docs/resilience.md` |
| Queue (BullMQ on Upstash, inline fallback) + worker | ✅ | — | core, notifications | `python -m app.worker` |
| Scheduler (daily/weekly tasks, Redis lock) | ✅ | ✅ | reminders | `/api/admin/scheduler` |
| Assistant service (Groq + rules fallback) | ✅ | — | core, learning, knowledge, identity | no "AI" in UI |
| Demo company seed | ✅ | — | seed | `python -m app.cli seed` |
| Migrations (Alembic) + drift test | ✅ | — | core | |
| i18n English/Hindi (navigation, home, login, banners) | — | 🟡 | | content strings in English; Hindi files ready for more keys |

| Admin monitoring (server, API load, DB, Redis/BullMQ, scheduler, breakers, errors; live SSE) | ✅ `/admin/monitoring` | ✅ | monitoring, e2e | |
| Splash screen, Motion animations, limited-mode banner | — | ✅ | e2e | |
| Single top navigation (both apps), light two-colour theme, full-width layouts | — | ✅ | e2e | 2026-10-10 UI pass |
| People directory for pickers | ✅ `/people` | ✅ | identity | |

## Core flows (docs/core-flows.md)
| Feature | Backend | Frontend | Tests |
|---|---|---|---|
| Self sign-up with job role (setting `identity.allow_self_signup`, allowed email domains) | ✅ `/auth/signup`, `/auth/signup-options` | ✅ `/signup` | core_flows |
| Role skills on profile with separate states (needed · training · proven) | ✅ `/me/skills` | ✅ profile, home | core_flows |
| Assign by skill (everyone whose role needs it) + by name, full preview, no duplicates | ✅ audience `skill_id` | ✅ `/admin/assign` | core_flows |
| Only selected people notified | ✅ | — | core_flows |
| Every course-test attempt kept (answers, score, pass) + tries limit | ✅ `course_quiz_attempts` | ✅ | core_flows, learning |
| HR training tracker: not started · in progress · course done · failed · passed · overdue, CSV | ✅ `/admin/training` | ✅ `/admin/training` | core_flows |
| Landing page `/`, home moved to `/home` | — | ✅ | e2e |
| Due-date reminders 7/2/0 days, overdue list to managers next day, result to employee, daily results summary to HR + managers | ✅ 3 new workflows | ✅ Workflows page | core_flows |
| Helpers: course from a brief, quiz writer (multiple choice + written cases, pass mark, time), assign from a plain-words request; every step shown; people approve | ✅ `/admin/helpers/*`, `agent_runs` | ✅ `/admin/helpers` | agents |
| Written answers scored against a rubric; unsure scores checked by the course expert before they count | ✅ `/admin/written-answers` | ✅ quiz + `/admin/answers` | learning |
| API call log (one line per call with time, user id, request id; slow calls flagged) | ✅ middleware | — | core |
| Message log: every channel attempt; email + WhatsApp simulated (no provider yet); phone number for WhatsApp | ✅ `/admin/message-log`, `delivery_logs` | ✅ `/admin/messages`, My reminders | core_flows |
| Learn: To do · Browse courses · Done | — | ✅ | e2e |

## Learner (L-01 … L-10)
| ID | Screen | Backend | Frontend | Tests |
|---|---|---|---|---|
| L-01 | Home: one next step, pathway progress, coming up | ✅ `/me/home` | ✅ | insights, seed |
| L-02 | My pathway: waves of 3, learn/practise/connect/prove | ✅ `/me/pathway` | ✅ | pathways |
| L-03 | Lesson with captions, simulation (AR + simple mode), quiz (score + x of y right; answers only after a pass; tries limited by `learning.quiz_max_attempts`) | ✅ | ✅ | learning |
| L-04 | Skill check: intro, one question per screen, result with level/rank | ✅ | ✅ | assessments |
| L-05 | Catalogue | ✅ `/courses` | ✅ | learning |
| L-06 | Mandatory proctored test, consent, in-person option, certificates | ✅ | ✅ | assessments, certificates |
| L-07 | Career map: up/sideways, readiness, add to pathway | ✅ `/me/career` | ✅ | insights |
| L-08 | Leaderboards (live SSE), compliance by department | ✅ | ✅ | gamification |
| L-09 | Points, level, streak, badges, team challenge | ✅ | ✅ | gamification |
| L-10 | My reminders (window, channels) | ✅ `/me/preferences` | ✅ | identity, reminders |

## Manager & admin
| ID | Screen | Backend | Frontend | Tests |
|---|---|---|---|---|
| M-01..03 | Team counts, skills heatmap, needs attention + nudge, approvals | ✅ `/team` | ✅ | insights, pathways |
| A-01 | Admin home: quick actions, live numbers, needs attention, content gaps | ✅ `/admin/home` | ✅ | reports |
| A-02 | Upload employees, role suggestions | ✅ | ✅ | identity |
| A-03 | Roles and required skills; send skill tests (preview + undo) | ✅ | ✅ | skills, assessments |
| A-04 | Ranking by skill | ✅ | ✅ | skills |
| A-05 | Course builder: draft from a document → expert approval | ✅ | ✅ | learning |
| A-06 | Sessions & invitations; self-paced reminders preview/send | ✅ | ✅ | learning, reminders |
| A-07 | Workflows: manual/hybrid/auto, preview, approve, stop all | ✅ | ✅ | workflows |
| A-08 | Reports: 15 standard reports, drill-down, Excel/CSV/PDF, schedules | ✅ | ✅ | reports |
| A-09 | Proctoring review: queue, evidence, decision with note, appeal | ✅ | ✅ | assessments |
| A-10, A-11 | Settings | ✅ `/settings` | ✅ | |

## Knowledge Hub (K-01 … K-13)
| ID | Screen | Backend | Frontend | Tests |
|---|---|---|---|---|
| — | Knowledge Hub access: records staff only (roles + owners/backups/category heads), enforced on every `/api/knowledge` route | ✅ | ✅ | knowledge, e2e |
| K-01 | Home: search/ask, types, spaces, recently verified, critical, my items | ✅ | ✅ | knowledge |
| K-02 | Add knowledge in three clicks: write/upload/link, suggestions, duplicate check | ✅ | ✅ | knowledge |
| K-03 | Knowledge page: owner, version, review, actions | ✅ | ✅ | knowledge |
| K-05 | Access & owners: roles, requests, items without owner | ✅ | ✅ | knowledge |
| K-06 | Simple data lists: import, filter, row history | ✅ | ✅ | knowledge |
| K-07 | Library: by type/category, filters, bulk actions | ✅ | ✅ | knowledge |
| K-08 | Versions, revisions, reviews; compare; restore | ✅ | ✅ | knowledge |
| K-09 | My items worklist | ✅ | ✅ | knowledge |
| K-10 | Reminder ladder (8 stages, combined daily message) | ✅ | ✅ | knowledge |
| K-11 | Leader dashboard: health score, trend, by function, attention | ✅ | ✅ | knowledge |
| K-12 | Function dashboard: by category, by owner, actions | ✅ | ✅ | knowledge |
| K-13 | Categories: add, rename, move, merge | ✅ | ✅ | knowledge |

## Delivery
| Item | Status |
|---|---|
| Dockerfiles (API, worker, web), docker-compose | ✅ |
| CI (lint, tests, build) and CD (images, deploy) | ✅ |
| Single-exe build | ⬜ planned (later, as agreed) |
| E2E tests (Playwright) | ✅ |
