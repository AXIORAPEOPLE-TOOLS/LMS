"""Background worker: consumes the job queues (BullMQ or SQS) and runs the scheduler.

    uv run python -m app.worker

The API only enqueues work (after its transaction commits); this process does it.
Which queue is used follows LMS_DEPLOY_PROFILE (development: inline, single: BullMQ, scalable: SQS).
If the queue is unreachable the API runs a few jobs inline and the redeliver sweep catches the rest.
"""

import asyncio
import contextlib
import logging
import signal
import time
from typing import Any, cast

from app.core.config import get_settings
from app.core.database import get_database
from app.core.logging import configure_logging
from app.core.queue import Queues, run_job
from app.main import wire_modules
from app.modules.scheduler.runner import Scheduler

logger = logging.getLogger("worker")


STATS = {"done": 0, "failed": 0, "last": "none yet"}
HEARTBEAT_SECONDS = 60


async def execute(name: str, data: dict[str, Any], job_id: str, attempt: int) -> Any:
    """Run one job with START/DONE/FAILED logs. Shared by the BullMQ and SQS consumers."""
    if name == "notifications.deliver":
        await RATE.wait()
    logger.info("START  %s (id %s, attempt %s) data=%s", name, job_id, attempt, data)
    started = time.perf_counter()
    try:
        result = await run_job(name, data)
    except Exception:
        STATS["failed"] += 1
        STATS["last"] = f"{name} FAILED"
        ms = (time.perf_counter() - started) * 1000
        settings = get_settings()
        if attempt < settings.job_attempts:
            wait = settings.job_backoff_ms * 2 ** (attempt - 1) // 1000
            logger.exception(
                "FAILED %s (id %s) after %.0f ms; retry %s of %s in about %s s",
                name,
                job_id,
                ms,
                attempt + 1,
                settings.job_attempts,
                wait,
            )
        else:
            logger.exception("FAILED %s (id %s) after %.0f ms; no retries left (dead-letter list)", name, job_id, ms)
        raise
    STATS["done"] += 1
    STATS["last"] = name
    logger.info("DONE   %s (id %s) in %.0f ms", name, job_id, (time.perf_counter() - started) * 1000)
    return result


async def process(job: Any, _token: str) -> Any:
    """BullMQ processor."""
    return await execute(job.name, job.data or {}, str(job.id), getattr(job, "attemptsMade", 0) + 1)


class RateLimit:
    """At most N deliveries per second across all workers (provider limits).

    BullMQ has this built in; for SQS a per-second counter in Redis is shared by every worker.
    Without Redis each worker keeps its own count (fine for one or two workers).
    """

    def __init__(self) -> None:
        self.enabled = False
        self.window = 0
        self.count = 0

    async def wait(self) -> None:
        settings = get_settings()
        if not self.enabled or settings.notification_rate_per_second <= 0:
            return
        while True:
            now = int(time.time())
            used = await self._shared(now) if settings.redis_url else self._local(now)
            if used <= settings.notification_rate_per_second:
                return
            await asyncio.sleep(1 - (time.time() % 1) + 0.01)

    def _local(self, now: int) -> int:
        if now != self.window:
            self.window, self.count = now, 0
        self.count += 1
        return self.count

    async def _shared(self, now: int) -> int:
        try:
            import redis.asyncio as redis

            client = redis.from_url(get_settings().redis_url, socket_connect_timeout=2, socket_timeout=2)
            try:
                key = f"lms:rate:deliver:{now}"
                used = int(await client.incr(key))
                if used == 1:
                    await client.expire(key, 5)
                return used
            finally:
                await client.aclose()
        except Exception:
            return self._local(now)  # Redis down: keep going with a per-worker limit


RATE = RateLimit()


async def _backlog() -> str:
    """Queue depth per queue, so a growing backlog is visible in the console."""
    from app.modules.monitoring.service import redis_stats

    try:
        stats = await redis_stats()
    except Exception:
        return "backlog unknown"
    if stats.get("status") != "up":
        return f"Redis {stats.get('status')}"
    parts = [
        f"{q['name']} {q['waiting']} waiting/{q['active']} active/{q['delayed']} later/{q['failed']} failed"
        for q in stats["queues"]
        if q["waiting"] or q["active"] or q["delayed"] or q["failed"]
    ]
    return "queues empty" if not parts else "; ".join(parts)


async def _sqs_backlog() -> str:
    from app.core.queue import get_queue
    from app.core.sqs_queue import SQSQueue

    queue = get_queue()
    if not isinstance(queue, SQSQueue):
        return "backlog unknown"
    parts = []
    for name in Queues.ALL:
        try:
            d = await queue.depth(name)
        except Exception:
            return "SQS unreachable"
        if any(d.values()):
            parts.append(
                f"{name} {d.get('waiting', 0)} waiting/{d.get('active', 0)} active/{d.get('delayed', 0)} later/"
                f"{d.get('dlq_waiting', 0)} dead-letter"
            )
    return "queues empty" if not parts else "; ".join(parts)


async def heartbeat(mode: str) -> None:
    while True:
        await asyncio.sleep(HEARTBEAT_SECONDS)
        if mode == "bullmq":
            backlog = await _backlog()
        elif mode == "sqs":
            backlog = await _sqs_backlog()
        else:
            backlog = "inline mode"
        logger.info(
            "alive (%s): since start %s done, %s failed, last: %s | %s",
            mode,
            STATS["done"],
            STATS["failed"],
            STATS["last"],
            backlog,
        )


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.environment)
    wire_modules()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):  # Windows has no add_signal_handler
            loop.add_signal_handler(sig, stop.set)

    logger.info(
        "Worker starting: profile=%s environment=%s queue_backend=%s storage=%s concurrency=%s per queue, retries=%s, "
        "scheduler every %ss",
        settings.deploy_profile,
        settings.environment,
        settings.queue_backend,
        settings.storage_backend,
        settings.worker_concurrency,
        settings.job_attempts,
        settings.scheduler_interval_seconds,
    )
    workers: list[Any] = []
    consumer_task: asyncio.Task[None] | None = None
    mode = "inline"
    if settings.queue_backend == "sqs":
        from app.core.queue import get_queue
        from app.core.sqs_queue import SQSConsumer, SQSQueue

        queue = get_queue()
        assert isinstance(queue, SQSQueue)
        RATE.enabled = True
        consumer_task = asyncio.create_task(SQSConsumer(queue, Queues.ALL, execute, stop).serve())
        mode = "sqs"
        where = settings.sqs_endpoint_url or f"AWS {settings.aws_region}"
        logger.info("Listening on SQS (%s): %s", where, ", ".join(f"{settings.sqs_queue_prefix}{q}" for q in Queues.ALL))
    elif settings.queue_backend == "bullmq" and settings.redis_url:
        mode = "bullmq"
        from bullmq import Queue, Worker

        for name in Queues.ALL:
            opts = {"connection": settings.redis_url, "concurrency": settings.worker_concurrency, "autorun": True}
            # bullmq's type hints say Future; it awaits coroutine functions like this one.
            workers.append(Worker(name, cast(Any, process), opts))
        logger.info("Listening on queues: %s", ", ".join(Queues.ALL))
        # Provider limits: at most N deliveries per second across every worker process.
        notifications = Queue(Queues.NOTIFICATIONS, {"connection": settings.redis_url})
        try:
            await notifications.setGlobalRateLimit(settings.notification_rate_per_second, 1000)
            logger.info("Delivery rate limit: %s per second", settings.notification_rate_per_second)
        except Exception:
            logger.warning("Could not set the delivery rate limit; continuing without it")
        finally:
            await notifications.close()
    else:
        logger.warning("Queue backend is inline: the API runs jobs itself. This worker only runs the scheduler.")

    scheduler: Scheduler | None = None
    if settings.scheduler_source == "worker":
        scheduler = Scheduler(settings.scheduler_interval_seconds)
        scheduler.start()
    else:
        logger.info("Scheduler runs from outside (EventBridge sends scheduler.run to the scheduled queue)")
    beat = asyncio.create_task(heartbeat(mode))
    logger.info("Worker ready. Waiting for jobs (Ctrl+C to stop).")
    try:
        await stop.wait()
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        beat.cancel()
        stop.set()
        if scheduler:
            await scheduler.stop()
        if consumer_task:
            await consumer_task  # finishes running jobs; unstarted messages stay in SQS
        for worker in workers:
            await worker.close()
        await get_database().dispose()


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
