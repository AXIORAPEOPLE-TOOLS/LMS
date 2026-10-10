from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.queue import job_handler
from app.modules.agents.service import AgentService


@job_handler("agents.run")
async def run_helper(session: AsyncSession, data: dict[str, Any]) -> None:
    await AgentService(session).execute(UUID(data["id"]))
