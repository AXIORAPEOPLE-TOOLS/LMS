# Resilience: degraded modes instead of errors

Rule: **a user never sees a raw 500 or a stack trace.** When a dependency fails, the product keeps
working in a reduced mode and says so in plain words.

## Components and fallbacks
| Component | Health key | If it fails | Mode |
|---|---|---|---|
| PostgreSQL (Neon) | `database` | Friendly 503 "We cannot reach the database right now. Nothing was lost." Breaker opens after 2 failures → requests fail fast for 15 s instead of hanging. The frontend shows last loaded data read-only. | `offline` |
| Redis / BullMQ | `queue` | Jobs run inline inside the API process. Breaker opens after 2 failures (2 s timeout) for 30 s. Scheduler runs without the Redis lock (tasks are idempotent). | `limited` |
| Groq (assistant) | `assistant` | Rules provider answers instead (drafts, suggestions, role matching, ask, helpers, written scoring). Breaker 3 failures / 60 s. | `limited` |
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

## Background jobs under load, and retries

| Concern | What happens | Setting |
|---|---|---|
| Sending to thousands at once | Jobs go to Redis in batches (one round trip per 200), so an assignment to 5,000 people takes seconds, not minutes | `LMS_ENQUEUE_BATCH_SIZE` |
| Throughput | Each worker runs N jobs at a time per queue; run more worker processes (any machine) to scale out. Queues are separate, so a big report never delays reminders | `LMS_WORKER_CONCURRENCY` (8) |
| Provider limits | At most N deliveries per second across all workers (BullMQ global rate limit) | `LMS_NOTIFICATION_RATE_PER_SECOND` (50) |
| A job crashes (DB blip, bug) | BullMQ retries with exponential backoff: 5 s, 10 s, 20 s, 40 s; after that it stays in the failed list (visible on Monitoring) | `LMS_JOB_ATTEMPTS` (5), `LMS_JOB_BACKOFF_MS` |
| A channel fails (email/WhatsApp provider) | That channel alone is retried (5 s, 10 s, 20 s); the in-app copy has already arrived; after repeated failures the breaker pauses the channel | `LMS_DELIVERY_RETRY_ATTEMPTS` (4) |
| The same job twice | Every job has an id (`name:id:attempt`), so a repeated enqueue is ignored; delivery locks the row and skips channels already done, so nobody gets a message twice | — |
| Redis down during a send | The request still succeeds. Up to 50 deliveries run inline; the rest stay in the database and the hourly `notifications.redeliver` sweep queues them when Redis is back. Nothing is lost | `LMS_INLINE_FALLBACK_LIMIT` |
| Is the worker busy? | The worker prints a heartbeat every minute with jobs done/failed and the backlog per queue (waiting / active / later / failed) | — |

Scheduled tasks run in only one worker at a time (Redis lock), so running three workers does not send three reminders.

## API call log
Every API call writes one line to the `api` logger:
`GET /api/courses?q=refund -> 200 in 34 ms (user=<id> ip=127.0.0.1 rid=4f2a9c1b7e30)`.
4xx are warnings, 5xx errors, and calls slower than `LMS_SLOW_REQUEST_MS` (1000) start with `SLOW`. The request id
is the same one the user sees in an error message, so a complaint can be matched to its line. Only the user id is
logged (no names or emails), and query values named token/password/key/secret are masked. Health and monitoring
polls are logged only when they fail or are slow. Turn it off with `LMS_LOG_REQUESTS=false`.

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
