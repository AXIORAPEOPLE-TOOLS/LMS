"""Undo window for bulk sends (golden rule 4), reused by every bulk feature."""

from collections.abc import Awaitable, Callable
from datetime import timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.modules.audit.service import AuditService
from app.modules.identity.models import User
from app.modules.learning.models import BulkAction
from app.modules.settings.service import SettingsService
from app.shared.clock import utcnow

UndoHandler = Callable[[AsyncSession, UUID], Awaitable[int]]
_UNDO_HANDLERS: dict[str, UndoHandler] = {}


def register_undo(kind: str, handler: UndoHandler) -> None:
    _UNDO_HANDLERS[kind] = handler


class BulkActionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def start(self, kind: str, actor: User | None, summary: str, count: int) -> BulkAction:
        minutes = await SettingsService(self.session).get("safety.undo_minutes")
        action = BulkAction(
            kind=kind,
            actor_id=actor.id if actor else None,
            summary=summary,
            count=count,
            undo_until=utcnow() + timedelta(minutes=minutes),
        )
        self.session.add(action)
        await self.session.flush()
        AuditService(self.session).record(
            f"bulk.{kind}", "bulk_action", action.id, actor_id=actor.id if actor else None, summary=summary, count=count
        )
        return action

    async def undo(self, action_id: UUID, actor: User) -> int:
        action = await self.session.get(BulkAction, action_id)
        if action is None:
            raise NotFoundError("We could not find that send.")
        if action.undone_at is not None:
            raise ConflictError("This was already undone.")
        if utcnow() > action.undo_until:
            raise ConflictError("The undo window has closed.")
        handler = _UNDO_HANDLERS.get(action.kind)
        if handler is None:
            raise ConflictError("This kind of send cannot be undone.")
        undone = await handler(self.session, action.id)
        action.undone_at = utcnow()
        AuditService(self.session).record("bulk.undo", "bulk_action", action.id, actor_id=actor.id, undone=undone)
        return undone
