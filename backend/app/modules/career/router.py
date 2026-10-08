from uuid import UUID

from fastapi import APIRouter

from app.core.deps import CurrentUser, SessionDep
from app.modules.career.service import CareerDetailOut, CareerMapOut, CareerService

router = APIRouter(prefix="/me/career", tags=["career"])


@router.get("", response_model=CareerMapOut)
async def career_map(session: SessionDep, user: CurrentUser) -> object:
    return await CareerService(session).map(user)


@router.get("/{role_id}", response_model=CareerDetailOut)
async def career_detail(role_id: UUID, session: SessionDep, user: CurrentUser) -> object:
    return await CareerService(session).detail(user, role_id)


@router.post("/{role_id}/add-to-pathway", status_code=204)
async def add_to_pathway(role_id: UUID, session: SessionDep, user: CurrentUser) -> None:
    await CareerService(session).add_to_pathway(user, role_id)


@router.post("/{role_id}/talk-to-manager", status_code=204)
async def talk_to_manager(role_id: UUID, session: SessionDep, user: CurrentUser) -> None:
    await CareerService(session).talk_to_manager(user, role_id)
