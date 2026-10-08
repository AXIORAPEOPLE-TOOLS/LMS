from typing import Any

from fastapi import APIRouter

from app.core.deps import AdminUser, SessionDep
from app.modules.audit.service import AuditService
from app.modules.settings.service import SettingsService
from app.shared.schemas import Schema

router = APIRouter(prefix="/settings", tags=["settings"])


class SettingOut(Schema):
    key: str
    value: Any
    default: Any
    description: str
    is_overridden: bool


class SettingIn(Schema):
    value: Any


@router.get("", response_model=list[SettingOut])
async def list_settings(session: SessionDep, _: AdminUser) -> object:
    return await SettingsService(session).all()


@router.put("/{key}", status_code=204)
async def update_setting(key: str, data: SettingIn, session: SessionDep, admin: AdminUser) -> None:
    await SettingsService(session).set(key, data.value, admin.id)
    AuditService(session).record("setting.changed", "setting", key, actor_id=admin.id, value=data.value)
