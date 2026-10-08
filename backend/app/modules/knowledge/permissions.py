"""Who can do what with a knowledge item (K-05). Only authorised owners decide.

            Read  Edit  Publish  Verify  Access
Viewer       ✓     –      –       –       –
Editor       ✓     ✓      –       –       –
Backup       ✓     ✓      –       ✓       –
Owner        ✓     ✓      ✓       ✓       ✓
Admin        ✓     ✓      ✓       ✓       ✓
"""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, PermissionDeniedError
from app.modules.identity.models import User
from app.modules.knowledge.models import KnowledgeAccess, KnowledgeItem, Visibility


def is_knowledge_admin(user: User) -> bool:
    return user.has_role("knowledge_admin", "admin")


@dataclass(frozen=True)
class Rights:
    read: bool
    edit: bool
    publish: bool
    verify: bool
    access: bool
    role: str  # owner | backup | editor | viewer | admin | none


class KnowledgePolicy:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _grants(self, item_id: UUID, user: User) -> set[str]:
        principals = [(KnowledgeAccess.principal_type == "user") & (KnowledgeAccess.principal_id == user.id)]
        if user.department_id:
            principals.append(
                (KnowledgeAccess.principal_type == "department") & (KnowledgeAccess.principal_id == user.department_id)
            )
        rows = (
            await self.session.scalars(select(KnowledgeAccess.role).where(KnowledgeAccess.item_id == item_id, or_(*principals)))
        ).all()
        return set(rows)

    async def rights(self, item: KnowledgeItem, user: User) -> Rights:
        if is_knowledge_admin(user):
            return Rights(True, True, True, True, True, "admin")
        if item.owner_id == user.id:
            return Rights(True, True, True, True, True, "owner")
        if item.backup_owner_id == user.id:
            return Rights(True, True, False, True, False, "backup")
        grants = await self._grants(item.id, user)
        if "editor" in grants:
            return Rights(True, True, False, False, False, "editor")
        visible = (
            item.visibility == Visibility.COMPANY.value
            or (item.visibility == Visibility.TEAM.value and item.team_department_id == user.department_id)
            or "viewer" in grants
        )
        if visible and item.status != "draft":
            return Rights(True, False, False, False, False, "viewer")
        return Rights(False, False, False, False, False, "none")

    async def get_readable(self, item_id: UUID, user: User) -> tuple[KnowledgeItem, Rights]:
        item = await self.session.get(KnowledgeItem, item_id)
        if item is None:
            raise NotFoundError("We could not find that item.")
        rights = await self.rights(item, user)
        if not rights.read:
            # Say it exists so people can ask for access, but show nothing inside.
            raise PermissionDeniedError("You do not have access to this item yet. You can ask the owner.")
        return item, rights

    def readable_filter(self, user: User):  # type: ignore[no-untyped-def]
        """SQL condition for 'items this person may see' (used by search and the Library)."""
        if is_knowledge_admin(user):
            return True
        granted = select(KnowledgeAccess.item_id).where(
            or_(
                (KnowledgeAccess.principal_type == "user") & (KnowledgeAccess.principal_id == user.id),
                (KnowledgeAccess.principal_type == "department") & (KnowledgeAccess.principal_id == user.department_id),
            )
        )
        return or_(
            KnowledgeItem.owner_id == user.id,
            KnowledgeItem.backup_owner_id == user.id,
            KnowledgeItem.id.in_(granted),
            (KnowledgeItem.status != "draft")
            & or_(
                KnowledgeItem.visibility == Visibility.COMPANY.value,
                (KnowledgeItem.visibility == Visibility.TEAM.value) & (KnowledgeItem.team_department_id == user.department_id),
            ),
        )
