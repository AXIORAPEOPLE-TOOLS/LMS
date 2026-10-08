from fastapi import APIRouter

from app.core.deps import ManagerUser, SessionDep
from app.modules.manager.service import ManagerService, NudgeIn, TeamOut

router = APIRouter(prefix="/team", tags=["manager"])


@router.get("", response_model=TeamOut)
async def team(session: SessionDep, manager: ManagerUser) -> object:
    return await ManagerService(session).team(manager)


@router.post("/nudge", status_code=204)
async def nudge(data: NudgeIn, session: SessionDep, manager: ManagerUser) -> None:
    await ManagerService(session).nudge(manager, data)
