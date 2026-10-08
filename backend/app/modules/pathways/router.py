from uuid import UUID

from fastapi import APIRouter

from app.core.deps import CurrentUser, ManagerUser, SessionDep
from app.core.errors import NotFoundError, PermissionDeniedError
from app.modules.identity.models import User
from app.modules.pathways.schemas import EvidenceIn, GenerateIn, PathwayOut
from app.modules.pathways.service import PathwayService
from app.shared.schemas import Schema

router = APIRouter(tags=["pathways"])


class SignOffIn(Schema):
    approve: bool = True


@router.get("/me/pathway", response_model=PathwayOut | None)
async def my_pathway(session: SessionDep, user: CurrentUser) -> object:
    return await PathwayService(session).view(user.id)


@router.post("/me/pathway/generate", response_model=PathwayOut)
async def generate_mine(data: GenerateIn, session: SessionDep, user: CurrentUser) -> object:
    service = PathwayService(session)
    await service.generate(user, user, target_role_id=data.target_role_id)
    return await service.view(user.id)


@router.post("/me/pathway/items/{item_id}/learned", status_code=204)
async def mark_learned(item_id: UUID, session: SessionDep, user: CurrentUser) -> None:
    await PathwayService(session).mark_learned(item_id, user)


@router.post("/me/pathway/items/{item_id}/evidence", status_code=204)
async def submit_evidence(item_id: UUID, data: EvidenceIn, session: SessionDep, user: CurrentUser) -> None:
    await PathwayService(session).submit_evidence(item_id, user, data.evidence)


@router.post("/me/pathway/items/{item_id}/connected", status_code=204)
async def mark_connected(item_id: UUID, session: SessionDep, user: CurrentUser) -> None:
    await PathwayService(session).mark_connected(item_id, user)


# ---- manager actions -----------------------------------------------------------------
async def _team_member(session: SessionDep, manager: User, user_id: UUID) -> User:
    person = await session.get(User, user_id)
    if person is None:
        raise NotFoundError("We could not find that person.")
    if person.manager_id != manager.id and not manager.has_role("admin"):
        raise PermissionDeniedError("This person is not in your team.")
    return person


@router.get("/users/{user_id}/pathway", response_model=PathwayOut | None)
async def person_pathway(user_id: UUID, session: SessionDep, manager: ManagerUser) -> object:
    await _team_member(session, manager, user_id)
    return await PathwayService(session).view(user_id)


@router.post("/users/{user_id}/pathway/generate", response_model=PathwayOut)
async def generate_for(user_id: UUID, data: GenerateIn, session: SessionDep, manager: ManagerUser) -> object:
    person = await _team_member(session, manager, user_id)
    service = PathwayService(session)
    await service.generate(person, manager, target_role_id=data.target_role_id)
    return await service.view(user_id)


@router.post("/pathways/{pathway_id}/approve", status_code=204)
async def approve(pathway_id: UUID, session: SessionDep, manager: ManagerUser) -> None:
    await PathwayService(session).approve(pathway_id, manager)


@router.post("/pathway-items/{item_id}/sign-off", status_code=204)
async def sign_off(item_id: UUID, data: SignOffIn, session: SessionDep, manager: ManagerUser) -> None:
    await PathwayService(session).sign_off(item_id, manager, data.approve)
