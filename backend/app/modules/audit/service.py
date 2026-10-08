from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.models import AuditLog


class AuditService:
    """Golden rule 7: overrides, exports, deletions, role changes and approvals are logged."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def record(
        self,
        action: str,
        entity_type: str,
        entity_id: Any = None,
        *,
        actor_id: UUID | None = None,
        **details: Any,
    ) -> AuditLog:
        entry = AuditLog(
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            details={k: _jsonable(v) for k, v in details.items()},
        )
        self.session.add(entry)
        return entry

    async def recent(self, *, entity_type: str | None = None, action: str | None = None, limit: int = 200) -> Sequence[AuditLog]:
        stmt = select(AuditLog).order_by(AuditLog.at.desc()).limit(limit)
        if entity_type:
            stmt = stmt.where(AuditLog.entity_type == entity_type)
        if action:
            stmt = stmt.where(AuditLog.action == action)
        return (await self.session.scalars(stmt)).all()


def _jsonable(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value
