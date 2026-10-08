"""Built-in scheduled tasks. Reminders and renewals run through workflows (so their mode applies)."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.queue import job_handler
from app.modules.scheduler.registry import scheduled_task


@scheduled_task("gamification.challenges", "daily")
async def settle_challenges(session: AsyncSession) -> int:
    from app.modules.gamification.service import GamificationService

    return await GamificationService(session).settle_challenges()


@scheduled_task("gamification.snapshots", "weekly")
async def board_snapshots(session: AsyncSession) -> int:
    """Remember this week's ranks so next week's boards can show movement."""
    from sqlalchemy import select

    from app.modules.gamification.service import BOARDS, GamificationService
    from app.modules.identity.models import User

    service = GamificationService(session)
    viewer = (await session.scalars(select(User).where(User.is_active.is_(True)).limit(1))).first()
    if viewer is None:
        return 0
    for board in BOARDS:
        if board == "skill_champions":
            continue
        data = await service.board(board, viewer, scope="company")
        await service.take_snapshot(data, f"{board}|company||")
    return len(BOARDS) - 1


@scheduled_task("proctoring.purge", "daily")
async def purge_snapshots(session: AsyncSession) -> int:
    from app.modules.assessments.service import AssessmentService

    return await AssessmentService(session).purge_old_snapshots()


@job_handler("scheduler.run")
async def run_scheduler_job(_: AsyncSession, data: dict[str, Any]) -> dict[str, str]:
    """Lets an admin (or an external cron) trigger the scheduler through the queue."""
    from app.core.database import get_database
    from app.modules.scheduler.registry import run_due_tasks

    return await run_due_tasks(get_database().session_factory, only=data.get("only"), force=bool(data.get("force")))
