# Resilience: degraded modes instead of errors

Rule: **a user never sees a raw 500 or a stack trace.** When a dependency fails, the product keeps
working in a reduced mode and says so in plain words.

## Components and fallbacks
| Component | Health key | If it fails | Mode |
|---|---|---|---|
| PostgreSQL (Neon) | `database` | Friendly 503 "We cannot reach the database right now. Nothing was lost." Breaker opens after 2 failures → requests fail fast for 15 s instead of hanging. The frontend shows last loaded data read-only. | `offline` |
| Redis / BullMQ | `queue` | Jobs run inline inside the API process. Breaker opens after 2 failures (2 s timeout) for 30 s. Scheduler runs without the Redis lock (tasks are idempotent). | `limited` |
| Groq (assistant) | `assistant` | Rules provider answers instead (drafts, suggestions, role matching, ask). Breaker 3 failures / 60 s. | `limited` |
| Email / WhatsApp | `email`, `whatsapp` | Channel status `failed`/`paused`; the in-app message always arrives. Per-channel breaker. | `limited` |
| File storage | `storage` | Uploads paused; everything else works. | `limited` |

`GET /api/health` → `{"mode": "full|limited|offline", "components": {...}, "degraded": [{"name","label","fallback"}]}`.
It always answers 200 (even with the database down) so the UI can explain what is happening.
`GET /api/health/live` is the container liveness probe.

### What counts as "database down"
Connection-level failures — the endpoint cannot be found or reached, authentication fails, too many
connections, server shutting down (SQLSTATE classes 08, 28, 53, 57P) or any error raised while
*connecting* (no SQL statement ran) — return 503 and trip the database breaker. A bad query is a bug and
returns a friendly 500 with a request id. See `is_connection_failure` in `app/core/errors.py`.

## Seeing it live
Admins open **Monitoring** (`/admin/monitoring`): every component's state, breaker states with a manual
reset, queue depths, latencies and the most recent errors with their request ids.

## Error contract
```json
{"error": {"code": "service_unavailable", "message": "…plain words…", "request_id": "a1b2c3d4e5f6", "details": [...]}}
```
Codes: `bad_request`, `unauthenticated`, `forbidden`, `not_found`, `conflict`, `validation_failed`,
`service_unavailable`, `unexpected`. Every response carries `X-Request-ID`; logs include it.

## Adding a new external service
1. Wrap calls: `await breaker("service-name").call(lambda: client.do(), timeout=5)`.
2. Catch `CircuitOpenError` and the call's errors → fallback behaviour.
3. `register_component(Component("service-name", "Plain label", check, fallback="What users still get"))`.
4. Add a test like `test/backend/core/test_resilience.py` (service down → fallback, breaker opens).
