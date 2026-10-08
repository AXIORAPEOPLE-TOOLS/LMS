"""Background loop that runs due tasks. Runs in the worker (or the API when enabled).

When several replicas run, a short Redis lock makes sure only one runs a tick;
if Redis is unavailable we still run (the per-task TaskRun row keeps it idempotent).
"""

import asyncio
import contextlib
import logging

from app.core.config import get_settings
from app.core.database import get_database
from app.core.resilience import breaker
from app.modules.scheduler.registry import run_due_tasks

logger = logging.getLogger("scheduler")
LOCK_KEY = "lms:scheduler:lock"


class Scheduler:
    def __init__(self, interval_seconds: int) -> None:
        self.interval = interval_seconds
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop(), name="lms-scheduler")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def _loop(self) -> None:
        while True:
            try:
                if await self._acquire_lock():
                    results = await run_due_tasks(get_database().session_factory)
                    if results:
                        logger.info("Scheduler ran: %s", results)
            except Exception:
                logger.exception("Scheduler tick failed")
            await asyncio.sleep(self.interval)

    async def _acquire_lock(self) -> bool:
        settings = get_settings()
        if not settings.redis_url:
            return True
        try:
            import redis.asyncio as redis

            async def _lock() -> bool:
                client = redis.from_url(settings.redis_url, socket_connect_timeout=3, socket_timeout=3)
                try:
                    return bool(await client.set(LOCK_KEY, "1", nx=True, ex=max(30, self.interval - 5)))
                finally:
                    await client.aclose()

            return await breaker("redis", failure_threshold=2).call(_lock, timeout=5)
        except Exception:
            return True  # degrade: run anyway, tasks are idempotent
