"""Points come only from real learning events published by other modules."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.gamification.service import GamificationService
from app.shared.events import DomainEvent, event_bus


async def _lesson(session: AsyncSession, event: DomainEvent) -> None:
    p = event.payload
    await GamificationService(session).award(p["user_id"], "lesson", p["lesson_id"], minutes=int(p.get("minutes") or 0))


async def _course(session: AsyncSession, event: DomainEvent) -> None:
    p = event.payload
    await GamificationService(session).award(p["user_id"], "course", p["course_id"])


async def _test(session: AsyncSession, event: DomainEvent) -> None:
    p = event.payload
    await GamificationService(session).award(p["user_id"], "test", p["test_id"])


async def _level(session: AsyncSession, event: DomainEvent) -> None:
    p = event.payload
    previous = p.get("previous")
    if previous is not None and p["level"] > previous:
        from uuid import uuid5

        # One award per level reached in this skill.
        ref = uuid5(p["skill_id"], str(p["level"]))
        await GamificationService(session).award(p["user_id"], "level_up", ref)


async def _certificate(session: AsyncSession, event: DomainEvent) -> None:
    p = event.payload
    await GamificationService(session).award(p["user_id"], "certificate", p["certificate_id"])


event_bus.subscribe("lesson.completed", _lesson)
event_bus.subscribe("course.completed", _course)
event_bus.subscribe("test.completed", _test)
event_bus.subscribe("skill.level_recorded", _level)
event_bus.subscribe("certificate.issued", _certificate)
