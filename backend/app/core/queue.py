"""Background job queue (BullMQ on Redis, or inline for tests/offline dev).

Usage from any service:

    defer_job(session, Queues.NOTIFICATIONS, "notifications.deliver", {"id": "..."})

Jobs are held on the SQLAlchemy session and only dispatched *after* the
transaction commits, so a worker never sees a job for data that was rolled back.
Handlers are registered with `@job_handler("name")` and receive a fresh session.

Under load: jobs go to Redis in batches (`enqueue_batch_size` per round trip), each job
carries an id so a repeated enqueue is ignored, crashed jobs retry with exponential
backoff (`job_attempts`, `job_backoff_ms`), and if Redis is down only a few jobs run
inline - undelivered notifications are picked up by the `notifications.redeliver` sweep.
"""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.resilience import breaker

logger = logging.getLogger(__name__)

PENDING_KEY = "pending_jobs"


class Queues:
    NOTIFICATIONS = "notifications"
    AUTHORING = "authoring"  # document drafting, knowledge suggestions
    REPORTS = "reports"
    SCHEDULED = "scheduled"  # reminder runs, renewals, ladders
    ALL = (NOTIFICATIONS, AUTHORING, REPORTS, SCHEDULED)


@dataclass
class Job:
    queue: str
    name: str
    data: dict[str, Any] = field(default_factory=dict)
    delay_ms: int = 0


JobHandler = Callable[[AsyncSession, dict[str, Any]], Awaitable[Any]]
_HANDLERS: dict[str, JobHandler] = {}


def job_handler(name: str) -> Callable[[JobHandler], JobHandler]:
    def register(func: JobHandler) -> JobHandler:
        _HANDLERS[name] = func
        return func

    return register


def get_handler(name: str) -> JobHandler:
    if name not in _HANDLERS:
        raise LookupError(f"No handler registered for job '{name}'")
    return _HANDLERS[name]


def defer_job(session: AsyncSession, queue: str, name: str, data: dict[str, Any] | None = None, *, delay_ms: int = 0) -> None:
    session.info.setdefault(PENDING_KEY, []).append(Job(queue, name, _jsonable(data or {}), delay_ms))


class JobQueue(Protocol):
    async def enqueue(self, job: Job) -> None: ...
    async def enqueue_many(self, jobs: list[Job]) -> None: ...
    async def close(self) -> None: ...


class InlineQueue:
    """Runs each job right away in its own session. Used in tests and offline."""

    def __init__(self) -> None:
        self.history: list[Job] = []

    async def enqueue(self, job: Job) -> None:
        self.history.append(job)
        await run_job(job.name, job.data)

    async def enqueue_many(self, jobs: list[Job]) -> None:
        for job in jobs:
            await self.enqueue(job)

    async def close(self) -> None:
        return None


class BullMQQueue:
    """Publishes jobs to BullMQ queues on Redis (Upstash in production)."""

    def __init__(self, redis_url: str) -> None:
        self.redis_url = redis_url
        self._queues: dict[str, Any] = {}

    def _queue(self, name: str) -> Any:
        from bullmq import Queue

        if name not in self._queues:
            self._queues[name] = Queue(name, {"connection": self.redis_url})
        return self._queues[name]

    @staticmethod
    def _opts(job: Job) -> dict[str, Any]:
        settings = get_settings()
        opts: dict[str, Any] = {
            "attempts": settings.job_attempts,
            "backoff": {"type": "exponential", "delay": settings.job_backoff_ms},
            "removeOnComplete": 1_000,
            "removeOnFail": 5_000,
        }
        if job.delay_ms:
            opts["delay"] = job.delay_ms
        if job.data.get("id"):
            # Same job twice (e.g. a retried request) -> BullMQ keeps one.
            run = f":{job.data['run']}" if job.data.get("run") else ""
            opts["jobId"] = f"{job.name}:{job.data['id']}:{job.data.get('attempt', 1)}{run}"
        return opts

    async def enqueue(self, job: Job) -> None:
        queue = self._queue(job.queue)
        # Breaker: if Redis keeps failing we skip it for a while and run inline.
        await breaker("redis", failure_threshold=2).call(lambda: queue.add(job.name, job.data, self._opts(job)), timeout=2)

    async def enqueue_many(self, jobs: list[Job]) -> None:
        """One Redis round trip per batch instead of one per job (bulk sends to thousands of people)."""
        size = max(1, get_settings().enqueue_batch_size)
        by_queue: dict[str, list[Job]] = {}
        for job in jobs:
            by_queue.setdefault(job.queue, []).append(job)
        for name, items in by_queue.items():
            queue = self._queue(name)
            for start in range(0, len(items), size):
                batch = [{"name": j.name, "data": j.data, "opts": self._opts(j)} for j in items[start : start + size]]
                await breaker("redis", failure_threshold=2).call(lambda b=batch, q=queue: q.addBulk(b), timeout=10)

    async def close(self) -> None:
        for queue in self._queues.values():
            await queue.close()
        self._queues.clear()


_queue: JobQueue | None = None


def get_queue() -> JobQueue:
    global _queue
    if _queue is None:
        settings = get_settings()
        if settings.queue_backend == "sqs":
            from app.core.sqs_queue import SQSQueue

            _queue = SQSQueue()
        elif settings.queue_backend == "bullmq" and settings.redis_url:
            _queue = BullMQQueue(settings.redis_url)
        else:
            _queue = InlineQueue()
    return _queue


def set_queue(queue: JobQueue | None) -> None:
    global _queue
    _queue = queue


# Jobs that a sweep can safely redo later if the queue (Redis or SQS) is down (the data is already in the database).
SWEEPABLE = {"notifications.deliver"}


async def dispatch_pending(session: AsyncSession) -> None:
    jobs: list[Job] = session.info.pop(PENDING_KEY, [])
    if not jobs:
        return
    queue = get_queue()
    try:
        if len(jobs) == 1:
            await queue.enqueue(jobs[0])
        else:
            await queue.enqueue_many(jobs)
        return
    except Exception:  # never fail a committed request because the queue blinked
        logger.exception("Could not enqueue %s jobs; falling back", len(jobs))
    limit = get_settings().inline_fallback_limit
    inline = [j for j in jobs if j.name not in SWEEPABLE] + [j for j in jobs if j.name in SWEEPABLE][: max(0, limit)]
    skipped = len(jobs) - len(inline)
    if skipped:
        logger.warning("%s deliveries left for the redeliver sweep (queue down, too many to run inline)", skipped)
    for job in inline:
        try:
            await run_job(job.name, job.data)
        except Exception:
            logger.exception("Inline job %s failed", job.name)


async def run_job(name: str, data: dict[str, Any]) -> Any:
    """Execute a job handler in a fresh transaction (used by worker and inline queue)."""
    from app.core.database import get_database

    handler = get_handler(name)
    async with get_database().session_factory() as session:
        try:
            result = await handler(session, data)
            await session.commit()
        except Exception:
            await session.rollback()
            raise
    await dispatch_pending(session)  # jobs may enqueue follow-up jobs
    return result


def _jsonable(value: Any) -> Any:
    from datetime import date, datetime
    from uuid import UUID

    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value
