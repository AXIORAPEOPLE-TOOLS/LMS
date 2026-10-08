from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pathways.service import PathwayService
from app.shared.events import DomainEvent, event_bus


async def _course_completed(session: AsyncSession, event: DomainEvent) -> None:
    await PathwayService(session).on_course_completed(event.payload["user_id"], event.payload["course_id"])


async def _level_recorded(session: AsyncSession, event: DomainEvent) -> None:
    p = event.payload
    await PathwayService(session).on_level_recorded(p["user_id"], p["skill_id"], p["level"])


event_bus.subscribe("course.completed", _course_completed)
event_bus.subscribe("skill.level_recorded", _level_recorded)
