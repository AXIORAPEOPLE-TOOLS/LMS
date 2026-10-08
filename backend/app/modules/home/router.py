from fastapi import APIRouter

from app.core.deps import CurrentUser, SessionDep
from app.modules.home.service import HomeOut, HomeService

router = APIRouter(tags=["home"])


@router.get("/me/home", response_model=HomeOut)
async def home(session: SessionDep, user: CurrentUser) -> object:
    return await HomeService(session).home(user)
