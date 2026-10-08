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
from typing import Any

from app.core.config import get_settings
from app.core.database import get_database
from app.core.logging import configure_logging
from app.core.queue import Queues, run_job
from app.main import wire_modules
from app.modules.scheduler.runner import Scheduler

logger = logging.getLogger("worker")


async def process(job: Any, _token: str) -> Any:
    logger.info("Running job %s (%s)", job.name, job.id)
    return await run_job(job.name, job.data or {})


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.environment)
    wire_modules()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):  # Windows has no add_signal_handler
            loop.add_signal_handler(sig, stop.set)

    workers: list[Any] = []
    if settings.queue_backend == "bullmq" and settings.redis_url:
        from bullmq import Worker

        for name in Queues.ALL:
            workers.append(Worker(name, process, {"connection": settings.redis_url, "concurrency": 4, "autorun": True}))
        logger.info("Listening on queues: %s", ", ".join(Queues.ALL))
    else:
        logger.warning("Queue backend is inline: the API runs jobs itself. This worker only runs the scheduler.")

    scheduler = Scheduler(settings.scheduler_interval_seconds)
    scheduler.start()
    try:
        await stop.wait()
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        await scheduler.stop()
        for worker in workers:
            await worker.close()
        await get_database().dispose()


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
