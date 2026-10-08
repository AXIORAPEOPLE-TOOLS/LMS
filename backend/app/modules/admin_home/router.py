from fastapi import APIRouter

from app.core.deps import AdminUser, SessionDep
from app.modules.admin_home.service import AdminHomeOut, AdminHomeService

router = APIRouter(tags=["admin"])


@router.get("/admin/home", response_model=AdminHomeOut)
async def admin_home(session: SessionDep, _: AdminUser) -> object:
    return await AdminHomeService(session).overview()
