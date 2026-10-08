"""Domain events and the scheduler feed the workflow engine."""

from datetime import time

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.scheduler.registry import scheduled_task
from app.modules.workflows.service import WorkflowEngine
from app.shared.events import DomainEvent, event_bus


async def _user_created(session: AsyncSession, event: DomainEvent) -> None:
    await WorkflowEngine(session).on_trigger("user.created", {"user_ids": [str(event.payload["user_id"])]})


async def _role_changed(session: AsyncSession, event: DomainEvent) -> None:
    await WorkflowEngine(session).on_trigger("user.role_changed", {"user_ids": [str(event.payload["user_id"])]})


async def _session_created(session: AsyncSession, event: DomainEvent) -> None:
    await WorkflowEngine(session).on_trigger("session.created", {"session_id": str(event.payload["session_id"])})


event_bus.subscribe("user.created", _user_created)
event_bus.subscribe("user.role_changed", _role_changed)
event_bus.subscribe("session.created", _session_created)


@scheduled_task("workflows.daily", "daily", not_before=time(8, 0))
async def daily(session: AsyncSession) -> int:
    return len(await WorkflowEngine(session).on_trigger("schedule:daily", {}, triggered_by="schedule"))


@scheduled_task("workflows.weekly", "weekly", not_before=time(8, 0))
async def weekly(session: AsyncSession) -> int:
    return len(await WorkflowEngine(session).on_trigger("schedule:weekly", {}, triggered_by="schedule"))
