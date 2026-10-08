from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter

from app.core.deps import AdminUser, SessionDep
from app.modules.audit.service import AuditService
from app.shared.schemas import Schema

router = APIRouter(prefix="/audit", tags=["audit"])


class AuditOut(Schema):
    id: UUID
    actor_id: UUID | None
    action: str
    entity_type: str
    entity_id: str | None
    details: dict[str, Any]
    at: datetime


@router.get("", response_model=list[AuditOut])
async def list_audit(
    session: SessionDep, _: AdminUser, entity_type: str | None = None, action: str | None = None, limit: int = 200
) -> object:
    return await AuditService(session).recent(entity_type=entity_type, action=action, limit=min(limit, 1000))
