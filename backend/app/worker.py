"""Background worker: consumes BullMQ queues and runs the scheduler.

    uv run python -m app.worker

The API only enqueues work (after its transaction commits); this process does it.
If Redis is unreachable the worker keeps the scheduler running, and the API falls
back to running jobs inline, so nothing is lost while Redis is down.
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


async def process(job: Any, _token: str) -> Any:
    attempt = getattr(job, "attemptsMade", 0) + 1
    logger.info("START  %s (id %s, attempt %s) data=%s", job.name, job.id, attempt, job.data or {})
    started = time.perf_counter()
    try:
        result = await run_job(job.name, job.data or {})
    except Exception:
        STATS["failed"] += 1
        STATS["last"] = f"{job.name} FAILED"
        ms = (time.perf_counter() - started) * 1000
        settings = get_settings()
        if attempt < settings.job_attempts:
            wait = settings.job_backoff_ms * 2 ** (attempt - 1) // 1000
            logger.exception(
                "FAILED %s (id %s) after %.0f ms; retry %s of %s in about %s s",
                job.name,
                job.id,
                ms,
                attempt + 1,
                settings.job_attempts,
                wait,
            )
        else:
            logger.exception("FAILED %s (id %s) after %.0f ms; no retries left (kept in the failed list)", job.name, job.id, ms)
        raise
    STATS["done"] += 1
    STATS["last"] = job.name
    logger.info("DONE   %s (id %s) in %.0f ms", job.name, job.id, (time.perf_counter() - started) * 1000)
    return result


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


async def heartbeat(mode: str) -> None:
    while True:
        await asyncio.sleep(HEARTBEAT_SECONDS)
        backlog = await _backlog() if mode == "bullmq" else "inline mode"
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
        "Worker starting: environment=%s queue_backend=%s concurrency=%s per queue, retries=%s, scheduler every %ss",
        settings.environment,
        settings.queue_backend,
        settings.worker_concurrency,
        settings.job_attempts,
        settings.scheduler_interval_seconds,
    )
    workers: list[Any] = []
    if settings.queue_backend == "bullmq" and settings.redis_url:
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

    scheduler = Scheduler(settings.scheduler_interval_seconds)
    scheduler.start()
    beat = asyncio.create_task(heartbeat("bullmq" if workers else "scheduler only"))
    logger.info("Worker ready. Waiting for jobs (Ctrl+C to stop).")
    try:
        await stop.wait()
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        beat.cancel()
        await scheduler.stop()
        for worker in workers:
            await worker.close()
        await get_database().dispose()


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
