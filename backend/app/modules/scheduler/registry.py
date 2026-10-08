"""Scheduled tasks. Each feature registers its own task with `@scheduled_task` (OCP)."""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.scheduler.models import TaskRun
from app.shared.clock import local_now, utcnow

logger = logging.getLogger("scheduler")

Every = Literal["hourly", "daily", "weekly"]
TaskFunc = Callable[[AsyncSession], Awaitable[Any]]


@dataclass(frozen=True)
class ScheduledTask:
    name: str
    every: Every
    func: TaskFunc
    not_before: time = time(0, 0)  # local time of day


_TASKS: dict[str, ScheduledTask] = {}


def scheduled_task(name: str, every: Every, *, not_before: time = time(0, 0)) -> Callable[[TaskFunc], TaskFunc]:
    def register(func: TaskFunc) -> TaskFunc:
        _TASKS[name] = ScheduledTask(name, every, func, not_before)
        return func

    return register


def tasks() -> list[ScheduledTask]:
    return list(_TASKS.values())


def is_due(task: ScheduledTask, last_run: datetime | None, now_local: datetime) -> bool:
    if now_local.time() < task.not_before:
        return False
    if last_run is None:
        return True
    last_local = last_run.astimezone(now_local.tzinfo)
    if task.every == "hourly":
        return now_local - last_local >= timedelta(minutes=55)
    if task.every == "daily":
        return last_local.date() < now_local.date()
    # weekly: once per ISO week, on or after Monday
    return last_local.isocalendar()[:2] < now_local.isocalendar()[:2]


async def run_due_tasks(session_factory: Callable[[], Any], *, only: str | None = None, force: bool = False) -> dict[str, str]:
    """Run every task that is due. Each task gets its own transaction; one failure never stops the others."""
    from app.core.queue import dispatch_pending

    results: dict[str, str] = {}
    now_local = local_now()
    for task in tasks():
        if only and task.name != only:
            continue
        async with session_factory() as session:
            record = await session.get(TaskRun, task.name)
            if not force and not is_due(task, record.last_run_at if record else None, now_local):
                continue
            try:
                outcome = await task.func(session)
                result = f"ok: {outcome}"
                if record is None:
                    session.add(TaskRun(name=task.name, last_run_at=utcnow(), last_result=result))
                else:
                    record.last_run_at, record.last_result = utcnow(), result
                await session.commit()
                await dispatch_pending(session)
            except Exception as exc:  # degrade: log, keep going, retry next tick
                await session.rollback()
                logger.exception("Scheduled task %s failed", task.name)
                result = f"failed: {type(exc).__name__}"
            results[task.name] = result
    return results
