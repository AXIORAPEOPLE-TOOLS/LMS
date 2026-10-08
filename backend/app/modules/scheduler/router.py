from datetime import datetime

from fastapi import APIRouter
from sqlalchemy import select

from app.core.database import get_database
from app.core.deps import AdminUser, SessionDep
from app.modules.audit.service import AuditService
from app.modules.scheduler.models import TaskRun
from app.modules.scheduler.registry import run_due_tasks, tasks
from app.shared.schemas import Schema

router = APIRouter(prefix="/admin/scheduler", tags=["scheduler"])


class TaskOut(Schema):
    name: str
    every: str
    last_run_at: datetime | None
    last_result: str | None


@router.get("", response_model=list[TaskOut])
async def list_tasks(session: SessionDep, _: AdminUser) -> list[TaskOut]:
    runs = {r.name: r for r in (await session.scalars(select(TaskRun))).all()}
    return [
        TaskOut(
            name=t.name,
            every=t.every,
            last_run_at=runs[t.name].last_run_at if t.name in runs else None,
            last_result=runs[t.name].last_result if t.name in runs else None,
        )
        for t in tasks()
    ]


@router.post("/{name}/run")
async def run_task(name: str, session: SessionDep, admin: AdminUser) -> dict[str, str]:
    """Everything automatic can also be done by hand (golden rule 6)."""
    AuditService(session).record("scheduler.run_manually", "task", name, actor_id=admin.id)
    await session.commit()
    return await run_due_tasks(get_database().session_factory, only=name, force=True)
