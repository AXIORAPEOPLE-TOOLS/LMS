"""Scheduled sessions send invitations (Accept / Decline). Self-paced items never do (A-06)."""

from collections.abc import Sequence
from datetime import timedelta
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.modules.audit.service import AuditService
from app.modules.identity.models import User
from app.modules.learning.bulk import BulkActionService, register_undo
from app.modules.learning.models import Invitation, InvitationStatus, LiveSession
from app.modules.learning.schemas import BulkResultOut, InvitationPreviewOut, SessionIn, SessionOut
from app.modules.notifications.models import NotificationKind
from app.modules.notifications.service import NotificationService
from app.shared.audience import Audience, resolve_audience
from app.shared.clock import utcnow
from app.shared.events import DomainEvent, event_bus


def invitation_text(first_name: str, session: LiveSession) -> str:
    return f'Hi {first_name}, you are invited to "{session.title}" on {session.starts_at:%a %d %b at %H:%M}. Can you join?'


class SessionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, session_id: UUID) -> LiveSession:
        live = await self.session.get(LiveSession, session_id)
        if live is None:
            raise NotFoundError("We could not find that session.")
        return live

    async def create(self, data: SessionIn, actor: User) -> LiveSession:
        audience = await resolve_audience(self.session, data.audience)
        live = LiveSession(**data.model_dump(exclude={"audience"}), audience_label=audience.label, created_by_id=actor.id)
        self.session.add(live)
        await self.session.flush()
        # Invitations are created now but only *sent* after the admin previews them.
        for user_id in audience.user_ids:
            self.session.add(Invitation(session_id=live.id, user_id=user_id))
        await self.session.flush()
        AuditService(self.session).record("session.created", "live_session", live.id, actor_id=actor.id)
        await event_bus.publish(self.session, DomainEvent("session.created", {"session_id": live.id}))
        return live

    async def preview(self, session_id: UUID) -> InvitationPreviewOut:
        live = await self.get(session_id)
        count = await self._count(live.id)
        return InvitationPreviewOut(
            audience_label=live.audience_label, people=count, message=invitation_text("{first name}", live)
        )

    async def preview_for(self, audience: Audience, title: str, starts_at_text: str) -> InvitationPreviewOut:
        resolved = await resolve_audience(self.session, audience)
        return InvitationPreviewOut(
            audience_label=resolved.label,
            people=len(resolved.user_ids),
            message=f'Hi {{first name}}, you are invited to "{title}" on {starts_at_text}. Can you join?',
        )

    async def send_invitations(self, session_id: UUID, actor: User | None, *, automatic: bool = False) -> BulkResultOut:
        live = await self.get(session_id)
        pending = (
            await self.session.scalars(select(Invitation).where(Invitation.session_id == live.id, Invitation.batch_id.is_(None)))
        ).all()
        if not pending:
            raise ConflictError("Everyone on the list has already been invited.")
        bulk = await BulkActionService(self.session).start(
            "send_invitations", actor, f'Invitations for "{live.title}"', len(pending)
        )
        names = dict(
            (await self.session.execute(select(User.id, User.full_name).where(User.id.in_([i.user_id for i in pending])))).all()
        )
        notifications = NotificationService(self.session)
        for invitation in pending:
            invitation.batch_id = bulk.id
            first = (names.get(invitation.user_id) or "there").split()[0]
            await notifications.notify(
                invitation.user_id,
                kind=NotificationKind.INVITATION,
                title=f'Invitation: "{live.title}"',
                body=invitation_text(first, live),
                link=f"/learn/sessions/{live.id}",
                actions=[
                    {"label": "Accept", "action": "rsvp_accept", "session_id": str(live.id)},
                    {"label": "Decline", "action": "rsvp_decline", "session_id": str(live.id)},
                ],
                related=("live_session", live.id),
                automatic=automatic,
            )
        live.invitations_sent_at = utcnow()
        await self.session.flush()
        return BulkResultOut(bulk_action_id=bulk.id, count=len(pending), undo_until=bulk.undo_until, summary=bulk.summary)

    async def respond(self, session_id: UUID, user: User, accept: bool) -> Invitation:
        invitation = (
            await self.session.scalars(
                select(Invitation).where(Invitation.session_id == session_id, Invitation.user_id == user.id)
            )
        ).first()
        if invitation is None:
            raise NotFoundError("You are not invited to this session.")
        invitation.status = (InvitationStatus.ACCEPTED if accept else InvitationStatus.DECLINED).value
        invitation.responded_at = utcnow()
        await self.session.flush()
        return invitation

    async def _count(self, session_id: UUID, status: str | None = None) -> int:
        stmt = select(func.count()).select_from(Invitation).where(Invitation.session_id == session_id)
        if status:
            stmt = stmt.where(Invitation.status == status)
        return int(await self.session.scalar(stmt) or 0)

    async def to_out(self, live: LiveSession, viewer: User | None = None) -> SessionOut:
        trainer = await self.session.get(User, live.trainer_id) if live.trainer_id else None
        my_status = None
        if viewer:
            mine = (
                await self.session.scalars(
                    select(Invitation.status).where(Invitation.session_id == live.id, Invitation.user_id == viewer.id)
                )
            ).first()
            my_status = mine
        return SessionOut.model_validate(live).model_copy(
            update={
                "trainer_name": trainer.full_name if trainer else None,
                "accepted": await self._count(live.id, InvitationStatus.ACCEPTED.value),
                "declined": await self._count(live.id, InvitationStatus.DECLINED.value),
                "waiting": await self._count(live.id, InvitationStatus.PENDING.value),
                "my_status": my_status,
            }
        )

    async def list_all(self, *, upcoming_only: bool = True) -> Sequence[LiveSession]:
        stmt = select(LiveSession).order_by(LiveSession.starts_at)
        if upcoming_only:
            stmt = stmt.where(LiveSession.ends_at >= utcnow() - timedelta(hours=1))
        return (await self.session.scalars(stmt)).all()

    async def for_user(self, user: User) -> Sequence[LiveSession]:
        stmt = (
            select(LiveSession)
            .join(Invitation, Invitation.session_id == LiveSession.id)
            .where(
                Invitation.user_id == user.id,
                Invitation.batch_id.is_not(None),
                LiveSession.ends_at >= utcnow(),
            )
            .order_by(LiveSession.starts_at)
        )
        return (await self.session.scalars(stmt)).all()


async def _undo_invitations(session: AsyncSession, batch_id: UUID) -> int:
    # Undo means "not sent": invitations go back to the unsent list; replies are cleared.
    invitations = (await session.scalars(select(Invitation).where(Invitation.batch_id == batch_id))).all()
    for invitation in invitations:
        invitation.batch_id = None
        invitation.status = InvitationStatus.PENDING.value
        invitation.responded_at = None
    from app.modules.notifications.models import Notification

    if invitations:
        await session.execute(
            delete(Notification).where(
                Notification.related_id == invitations[0].session_id,
                Notification.kind == NotificationKind.INVITATION.value,
                Notification.user_id.in_([i.user_id for i in invitations]),
            )
        )
    return len(invitations)


register_undo("send_invitations", _undo_invitations)
