from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.queue import job_handler
from app.modules.learning.course_service import CourseService
from app.modules.learning.schemas import DraftOptions


@job_handler("courses.draft_from_source")
async def draft_from_source(session: AsyncSession, data: dict[str, Any]) -> None:
    await CourseService(session).build_draft(UUID(data["course_id"]), DraftOptions(**data["options"]))
