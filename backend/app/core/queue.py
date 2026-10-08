"""Background job queue (BullMQ on Redis, or inline for tests/offline dev).

Usage from any service:

    defer_job(session, Queues.NOTIFICATIONS, "notifications.deliver", {"id": "..."})

Jobs are held on the SQLAlchemy session and only dispatched *after* the
transaction commits, so a worker never sees a job for data that was rolled back.
Handlers are registered with `@job_handler("name")` and receive a fresh session.
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
    async def close(self) -> None: ...


class InlineQueue:
    """Runs each job right away in its own session. Used in tests and offline."""

    def __init__(self) -> None:
        self.history: list[Job] = []

    async def enqueue(self, job: Job) -> None:
        self.history.append(job)
        await run_job(job.name, job.data)

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

    async def enqueue(self, job: Job) -> None:
        opts: dict[str, Any] = {
            "attempts": 5,
            "backoff": {"type": "exponential", "delay": 5_000},
            "removeOnComplete": 1_000,
            "removeOnFail": 5_000,
        }
        if job.delay_ms:
            opts["delay"] = job.delay_ms
        queue = self._queue(job.queue)
        # Breaker: if Redis keeps failing we skip it for a while and run inline.
        await breaker("redis", failure_threshold=2).call(lambda: queue.add(job.name, job.data, opts), timeout=2)

    async def close(self) -> None:
        for queue in self._queues.values():
            await queue.close()
        self._queues.clear()


_queue: JobQueue | None = None


def get_queue() -> JobQueue:
    global _queue
    if _queue is None:
        settings = get_settings()
        _queue = BullMQQueue(settings.redis_url) if settings.queue_backend == "bullmq" and settings.redis_url else InlineQueue()
    return _queue


def set_queue(queue: JobQueue | None) -> None:
    global _queue
    _queue = queue


async def dispatch_pending(session: AsyncSession) -> None:
    jobs: list[Job] = session.info.pop(PENDING_KEY, [])
    queue = get_queue()
    for job in jobs:
        try:
            await queue.enqueue(job)
        except Exception:  # never fail a committed request because Redis blinked
            logger.exception("Could not enqueue job %s; running it inline", job.name)
            await run_job(job.name, job.data)


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
