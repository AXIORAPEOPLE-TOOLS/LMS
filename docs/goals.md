# Goals

## Product goals
| Goal | Measure | Target |
|---|---|---|
| Everyone knows their next step | % of active learners who open their next step weekly | ≥ 70% |
| Close role gaps | Average gap levels per person, quarter on quarter | −25% |
| Mandatory training on time | On-time compliance by department | ≥ 90% |
| Calm reminders | Reminders per person per week | ≤ 3 (enforced) |
| Knowledge stays current | Knowledge health score / current-on-time | ≥ 85 / ≥ 90% |
| Knowledge is findable | Search success (searches with results) | ≥ 70% |
| Fast setup | Non-technical user builds a list from a spreadsheet | < 5 minutes |

## Engineering goals
- **Modular monolith**: one deployable API + one worker, features isolated in modules with clear contracts; can be split later.
- **Robustness**: degrade instead of failing (database, Redis, Groq, email, WhatsApp, storage).
- **Testability**: pure rule functions; every feature has its own test folder; e2e before push.
- **Maintainability**: SOLID, small services, settings over constants, docs updated with code.
- **Operability**: health endpoint with modes, structured logs with request ids, audit trail.

## Non-goals (for now)
- Microservices, Kubernetes-specific features, multi-tenant isolation (single company per deployment).
- Building our own video/AR engine (we store scenario files and play them; AR is device-dependent).
