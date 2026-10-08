from uuid import UUID

from fastapi import APIRouter

from app.core.deps import AdminUser, CurrentUser, ManagerUser, SessionDep
from app.modules.skills.schemas import (
    JobRoleIn,
    JobRoleOut,
    ManualLevelIn,
    MySkillOut,
    RoleDetailOut,
    RoleSkillsReplace,
    SkillIn,
    SkillOut,
    SkillRankingOut,
)
from app.modules.skills.service import SkillsService

router = APIRouter(tags=["skills"])


@router.get("/skills", response_model=list[SkillOut])
async def list_skills(session: SessionDep, _: CurrentUser, q: str | None = None) -> object:
    return await SkillsService(session).list_skills(q)


@router.post("/skills", response_model=SkillOut, status_code=201)
async def create_skill(data: SkillIn, session: SessionDep, admin: AdminUser) -> object:
    return await SkillsService(session).create_skill(data, admin)


@router.get("/skills/{skill_id}/ranking", response_model=SkillRankingOut)
async def skill_ranking(skill_id: UUID, session: SessionDep, user: CurrentUser) -> object:
    return await SkillsService(session).ranking(skill_id, user)


@router.get("/job-roles", response_model=list[JobRoleOut])
async def list_roles(session: SessionDep, _: CurrentUser, q: str | None = None) -> object:
    return await SkillsService(session).list_roles(q)


@router.post("/job-roles", response_model=JobRoleOut, status_code=201)
async def create_role(data: JobRoleIn, session: SessionDep, admin: AdminUser) -> object:
    return await SkillsService(session).create_role(data, admin)


@router.get("/job-roles/{role_id}", response_model=RoleDetailOut)
async def role_detail(role_id: UUID, session: SessionDep, _: CurrentUser) -> object:
    return await SkillsService(session).role_detail(role_id)


@router.put("/job-roles/{role_id}/skills", response_model=RoleDetailOut)
async def replace_role_skills(role_id: UUID, data: RoleSkillsReplace, session: SessionDep, admin: AdminUser) -> object:
    return await SkillsService(session).replace_role_skills(role_id, data, admin)


@router.get("/me/skills", response_model=list[MySkillOut])
async def my_skills(session: SessionDep, user: CurrentUser) -> object:
    return await SkillsService(session).my_skills(user)


@router.put("/users/{user_id}/skills/{skill_id}/level", status_code=204)
async def override_level(user_id: UUID, skill_id: UUID, data: ManualLevelIn, session: SessionDep, actor: ManagerUser) -> None:
    await SkillsService(session).set_level_manually(user_id, skill_id, data.level, data.reason, actor)
