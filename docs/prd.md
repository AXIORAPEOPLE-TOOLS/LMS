# Product Requirements — Learning & Knowledge Suite

Sources: *LMS_UIUX_Deck.pdf* (32 slides, screen IDs) and *LMS_Build_Spec.pdf* (build specification v3, sheets 01–24).

## 1. Problem
Service companies hire many people into well-defined roles but cannot see who is ready for what.
Training is assigned by hand, reminders are noisy, mandatory compliance (POSH, DPDP) is chased in
spreadsheets, and company know-how (SOPs, policies, registers) lives in scattered drives with no owner.

## 2. Product in one paragraph
Every employee is mapped to a **role**; every role has **required skills**; every skill has a **test**.
Test results give each person a **level (0–5)** and a **rank** per skill. Gaps become a **pathway** of
waves (3 skills each; every skill goes *learn → practise → connect → prove*). Courses are built from a
company's own documents, some with simulations (AR where supported, a simple tap mode everywhere).
Gentle **reminders** arrive at each person's best time; scheduled sessions send **invitations**.
Mandatory training can be **proctored**, always with consent and an in-person alternative, and ends in
a **verifiable certificate**. **Gamification** and **live leaderboards** keep people engaged.
**Career maps** show up and sideways moves with readiness. Every **workflow** is manual, hybrid or
automatic. **Reports** export to Excel, CSV and PDF. A separate **Knowledge Hub** stores, finds, reviews
and controls SOPs, policies and lists, with versions, owners, reminders and leader dashboards.

## 3. Users
| User | Main jobs | Screens |
|---|---|---|
| Learner | See next step, take skill checks, learn, get certified, grow | L-01 … L-10 |
| Manager | See team status, nudge, approve pathways and practice | M-01 … M-03 |
| L&D admin | People & roles, tests, courses, sessions, workflows, reports, proctoring | A-01 … A-11 |
| Knowledge owner / admin / leader | Add, review, control and measure knowledge | K-01 … K-13 |

## 4. Golden rules (apply to every screen and feature)
1. One main action per screen. 2. Plain words (English + Hindi). 3. Always show what is next.
4. Safe by default: preview before sending to many, undo for 10 minutes. 5. Humans decide: assistant
drafts, people approve. 6. Everything can be done by hand; every workflow is Manual/Hybrid/Auto.
7. Everything important is logged. 8. Settings, not hard-coded numbers. 9. Mobile first, WCAG 2.1 AA.
10. Privacy first (DPDP).

Test for any screen: *could a new joiner on a low-cost phone finish the task without help in under a minute?*

## 5. Scope by area (MVP)
- **Identity**: sign-in, profile, preferences (language, reminder window & channels, name on boards), employee upload with role matching (A-02).
- **Skills**: catalogue, roles with required levels, career moves, levels from tests or manual override (audited), stack ranking (A-03/A-04).
- **Skill checks (L-04)**: one question per screen, timer, pause between skills, result with level, rank band and next step.
- **Pathways (L-02)**: waves of 3, four steps per skill, manager approval and practise sign-off, retest closes the skill.
- **Learning (L-03, L-05)**: catalogue, lessons with captions, simulations (ordered tap points), quiz with reasons, progress.
- **Course builder (A-05)**: upload SOP → draft lessons with page references + quiz → expert approval → publish.
- **Sessions & reminders (A-06, L-10)**: invitations with Accept/Decline; self-paced reminders inside the person's window (max 1/day, 3/week, quiet hours, no weekends/holidays), stop on completion.
- **Mandatory & certificates (L-06, A-09)**: consent notice, camera snapshots, flags reviewed by a person, appeal to a different reviewer, certificate with QR verification and renewal reminders 60/30/7 days.
- **Gamification (L-08, L-09)**: points only for real learning, levels, streaks, badges, team challenges, live boards, compliance by department only, hide-my-name.
- **Career (L-07)**: up/sideways options with readiness from tested skills only, add target to pathway, talk to manager.
- **Manager (M-01..03)**: counts, skills heatmap, needs attention + nudge, approvals.
- **Admin (A-01, A-07, A-08)**: live numbers, needs attention, content gaps; workflows with modes, preview, approval, stop-all; reports with drill-down, exports and schedules.
- **Knowledge Hub (K-01..K-13)**: search/ask, Library, add in three clicks with suggestions and duplicate check, page with owner/version/review, versions vs revisions vs reviews with compare/restore, My items, reminder ladder, access & requests, categories, data lists, leader and function dashboards.

## 6. Non-functional requirements
- **Robust**: no raw 500s; every external service has a fallback mode (see `resilience.md`).
- **Performance**: p95 API < 300 ms when deployed next to the database; boards update within 5 s.
- **Security**: Argon2 passwords, JWT, role checks on every route, audit log, watermarked exports.
- **Privacy**: proctoring pictures deleted 30 days after a case closes; every evidence view logged.
- **Portability**: Docker images, CI/CD, single-binary build.

## 7. Out of scope for MVP (V2/V3)
SSO (SAML/OIDC), real email/WhatsApp providers (interfaces ready), native mobile apps, AR rendering
(scenario format and fallback mode ready), Hindi translations of all content (i18n framework ready),
full-text search in Postgres (simple scoring now).
