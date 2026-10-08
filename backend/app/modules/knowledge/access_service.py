"""Access and owners (K-05): only authorised owners decide; everyone else asks in one click."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError, PermissionDeniedError, ValidationFailedError
from app.modules.audit.service import AuditService
from app.modules.identity.models import Department, User
from app.modules.knowledge.models import (
    ItemStatus,
    KnowledgeAccess,
    KnowledgeAccessRequest,
    KnowledgeItem,
)
from app.modules.knowledge.permissions import KnowledgePolicy, is_knowledge_admin
from app.modules.knowledge.presenter import Presenter
from app.modules.knowledge.schemas import AccessEntryOut, AccessOut, AccessRequestOut, GrantIn, ItemSummaryOut
from app.modules.notifications.models import NotificationKind
from app.modules.notifications.service import NotificationService

RIGHTS_TEXT = {
    "owner": "Edit, publish, verify, change access",
    "backup": "Edit, verify",
    "editor": "Edit drafts",
    "viewer": "Read and comment",
}


def _initials(name: str) -> str:
    return "".join(p[0] for p in name.split()[:2]).upper() or "?"


class AccessService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.policy = KnowledgePolicy(session)
        self.audit = AuditService(session)

    async def _item(self, item_id: UUID) -> KnowledgeItem:
        item = await self.session.get(KnowledgeItem, item_id)
        if item is None:
            raise NotFoundError("We could not find that item.")
        return item

    async def view(self, item_id: UUID, user: User) -> AccessOut:
        item = await self._item(item_id)
        rights = await self.policy.rights(item, user)
        if not (rights.read or rights.access):
            raise PermissionDeniedError("You do not have access to this item yet.")
        names = await Presenter(self.session).names({item.owner_id, item.backup_owner_id})
        entries: list[AccessEntryOut] = []
        if item.owner_id:
            n = names.get(item.owner_id, "Owner")
            entries.append(
                AccessEntryOut(
                    principal_type="owner",
                    principal_id=item.owner_id,
                    name=n,
                    initials=_initials(n),
                    role="Owner",
                    rights=RIGHTS_TEXT["owner"],
                )
            )
        if item.backup_owner_id:
            n = names.get(item.backup_owner_id, "Backup")
            entries.append(
                AccessEntryOut(
                    principal_type="backup",
                    principal_id=item.backup_owner_id,
                    name=n,
                    initials=_initials(n),
                    role="Backup owner",
                    rights=RIGHTS_TEXT["backup"],
                )
            )
        grants = (await self.session.scalars(select(KnowledgeAccess).where(KnowledgeAccess.item_id == item.id))).all()
        user_names = await Presenter(self.session).names({g.principal_id for g in grants if g.principal_type == "user"})
        depts = {d.id: d.name for d in (await self.session.scalars(select(Department))).all()}
        for g in sorted(grants, key=lambda g: (g.role != "editor", g.principal_type)):
            if g.principal_type == "user":
                n = user_names.get(g.principal_id, "Person")
            else:
                n = f"{depts.get(g.principal_id, 'Team')} team"
            entries.append(
                AccessEntryOut(
                    principal_type=g.principal_type,
                    principal_id=g.principal_id,
                    name=n,
                    initials=_initials(n),
                    role=g.role.title(),
                    rights=RIGHTS_TEXT[g.role],
                )
            )
        if item.visibility == "company":
            entries.append(
                AccessEntryOut(
                    principal_type="everyone",
                    principal_id=None,
                    name="Everyone",
                    initials="All",
                    role="Viewer",
                    rights=RIGHTS_TEXT["viewer"],
                )
            )
        elif item.visibility == "team" and item.team_department_id:
            n = f"{depts.get(item.team_department_id, 'Team')} team"
            entries.append(
                AccessEntryOut(
                    principal_type="department",
                    principal_id=item.team_department_id,
                    name=n,
                    initials=_initials(n),
                    role="Viewer",
                    rights=RIGHTS_TEXT["viewer"],
                )
            )
        requests = await self.requests(item_ids=[item.id]) if rights.access else []
        return AccessOut(item_id=item.id, item_title=item.title, entries=entries, requests=requests, can_change=rights.access)

    async def _require_access_right(self, item: KnowledgeItem, user: User) -> None:
        if not (await self.policy.rights(item, user)).access:
            raise PermissionDeniedError("Only the owner and knowledge admins can change access.")

    async def grant(self, item_id: UUID, data: GrantIn, user: User) -> None:
        item = await self._item(item_id)
        await self._require_access_right(item, user)
        model = User if data.principal_type == "user" else Department
        if await self.session.get(model, data.principal_id) is None:
            raise ValidationFailedError("That person or team does not exist.")
        existing = (
            await self.session.scalars(
                select(KnowledgeAccess).where(
                    KnowledgeAccess.item_id == item.id,
                    KnowledgeAccess.principal_type == data.principal_type,
                    KnowledgeAccess.principal_id == data.principal_id,
                )
            )
        ).first()
        if existing:
            existing.role = data.role
        else:
            self.session.add(KnowledgeAccess(item_id=item.id, **data.model_dump()))
        self.audit.record("knowledge.access_granted", "knowledge_item", item.id, actor_id=user.id, **data.model_dump())

    async def revoke(self, item_id: UUID, principal_type: str, principal_id: UUID, user: User) -> None:
        item = await self._item(item_id)
        await self._require_access_right(item, user)
        grant = (
            await self.session.scalars(
                select(KnowledgeAccess).where(
                    KnowledgeAccess.item_id == item.id,
                    KnowledgeAccess.principal_type == principal_type,
                    KnowledgeAccess.principal_id == principal_id,
                )
            )
        ).first()
        if grant is None:
            raise NotFoundError("That access does not exist.")
        await self.session.delete(grant)
        self.audit.record(
            "knowledge.access_removed",
            "knowledge_item",
            item.id,
            actor_id=user.id,
            principal_type=principal_type,
            principal_id=principal_id,
        )

    async def request(self, item_id: UUID, user: User, role: str, reason: str) -> KnowledgeAccessRequest:
        item = await self._item(item_id)
        rights = await self.policy.rights(item, user)
        if (role == "viewer" and rights.read) or (role == "editor" and rights.edit):
            raise ConflictError("You already have this access.")
        pending = (
            await self.session.scalars(
                select(KnowledgeAccessRequest).where(
                    KnowledgeAccessRequest.item_id == item.id,
                    KnowledgeAccessRequest.requester_id == user.id,
                    KnowledgeAccessRequest.status == "pending",
                )
            )
        ).first()
        if pending:
            return pending
        request = KnowledgeAccessRequest(item_id=item.id, requester_id=user.id, role=role, reason=reason)
        self.session.add(request)
        await self.session.flush()
        if item.owner_id:
            await NotificationService(self.session).notify(
                item.owner_id,
                kind=NotificationKind.KNOWLEDGE,
                title=f'{user.full_name} asks to {"view" if role == "viewer" else "edit"} "{item.title}"',
                body=reason,
                link=f"/knowledge/items/{item.id}/access",
                related=("knowledge_item", item.id),
            )
        return request

    async def decide(self, request_id: UUID, approve: bool, user: User) -> KnowledgeAccessRequest:
        request = await self.session.get(KnowledgeAccessRequest, request_id)
        if request is None or request.status != "pending":
            raise NotFoundError("There is no open request here.")
        item = await self._item(request.item_id)
        await self._require_access_right(item, user)
        request.status = "approved" if approve else "declined"
        request.decided_by_id = user.id
        if approve:
            await self.grant(item.id, GrantIn(principal_type="user", principal_id=request.requester_id, role=request.role), user)
        await NotificationService(self.session).notify(
            request.requester_id,
            kind=NotificationKind.KNOWLEDGE,
            title=f'Your access request for "{item.title}" was {"approved" if approve else "declined"}',
            link=f"/knowledge/items/{item.id}",
            related=("knowledge_item", item.id),
        )
        return request

    async def requests(self, *, item_ids: Sequence[UUID] | None = None, owner: User | None = None) -> list[AccessRequestOut]:
        stmt = (
            select(KnowledgeAccessRequest, KnowledgeItem.title)
            .join(KnowledgeItem, KnowledgeItem.id == KnowledgeAccessRequest.item_id)
            .where(KnowledgeAccessRequest.status == "pending")
            .order_by(KnowledgeAccessRequest.created_at)
        )
        if item_ids is not None:
            stmt = stmt.where(KnowledgeAccessRequest.item_id.in_(item_ids))
        if owner is not None and not is_knowledge_admin(owner):
            stmt = stmt.where(KnowledgeItem.owner_id == owner.id)
        rows = (await self.session.execute(stmt)).all()
        names = await Presenter(self.session).names({r.requester_id for r, _ in rows})
        return [
            AccessRequestOut(
                id=r.id,
                item_id=r.item_id,
                item_title=t,
                requester_id=r.requester_id,
                requester_name=names.get(r.requester_id, "Someone"),
                role=r.role,
                reason=r.reason,
                status=r.status,
                created_at=r.created_at,
            )
            for r, t in rows
        ]

    async def without_owner(self, user: User) -> list[ItemSummaryOut]:
        if not is_knowledge_admin(user) and not user.has_role("function_head"):
            raise PermissionDeniedError("Only knowledge admins can see this list.")
        items = (
            await self.session.scalars(
                select(KnowledgeItem).where(KnowledgeItem.owner_id.is_(None), KnowledgeItem.status != ItemStatus.ARCHIVED.value)
            )
        ).all()
        return await Presenter(self.session).summaries(items)

    async def assign_owner(self, item_id: UUID, owner_id: UUID, user: User) -> None:
        if not is_knowledge_admin(user) and not user.has_role("function_head"):
            raise PermissionDeniedError("Only knowledge admins can assign owners.")
        item = await self._item(item_id)
        if await self.session.get(User, owner_id) is None:
            raise ValidationFailedError("That person does not exist.")
        item.owner_id = owner_id
        await NotificationService(self.session).notify(
            owner_id,
            kind=NotificationKind.KNOWLEDGE,
            title=f'You are now the owner of "{item.title}"',
            link=f"/knowledge/items/{item.id}",
            related=("knowledge_item", item.id),
        )
        self.audit.record("knowledge.owner_assigned", "knowledge_item", item.id, actor_id=user.id, owner_id=owner_id)
