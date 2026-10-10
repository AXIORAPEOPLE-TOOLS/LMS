"""Turns items into API summaries with names, paths and review status (batched, no N+1)."""

from collections.abc import Iterable, Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.models import User
from app.modules.knowledge import rules
from app.modules.knowledge.models import KIND_LABELS, KnowledgeCategory, KnowledgeItem
from app.modules.knowledge.schemas import ItemSummaryOut
from app.modules.settings.service import SettingsService
from app.shared.clock import today


class CategoryTree:
    def __init__(self, categories: Sequence[KnowledgeCategory]) -> None:
        self.by_id = {c.id: c for c in categories}

    def path(self, category_id: UUID | None) -> str | None:
        if category_id is None or category_id not in self.by_id:
            return None
        names: list[str] = []
        current: KnowledgeCategory | None = self.by_id[category_id]
        while current is not None and len(names) < 6:
            names.append(current.name)
            current = self.by_id.get(current.parent_id) if current.parent_id else None
        return " › ".join(reversed(names))

    def root_of(self, category_id: UUID | None) -> UUID | None:
        current = self.by_id.get(category_id) if category_id else None
        while current is not None and current.parent_id and current.parent_id in self.by_id:
            current = self.by_id[current.parent_id]
        return current.id if current else None

    def descendants(self, category_id: UUID) -> set[UUID]:
        found = {category_id}
        changed = True
        while changed:
            changed = False
            for c in self.by_id.values():
                if c.parent_id in found and c.id not in found:
                    found.add(c.id)
                    changed = True
        return found

    def roots(self) -> list[KnowledgeCategory]:
        return sorted((c for c in self.by_id.values() if c.parent_id is None), key=lambda c: (c.position, c.name))


class Presenter:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self._tree: CategoryTree | None = None
        self._due_soon: int | None = None

    async def tree(self) -> CategoryTree:
        if self._tree is None:
            self._tree = CategoryTree((await self.session.scalars(select(KnowledgeCategory))).all())
        return self._tree

    async def due_soon_days(self) -> int:
        if self._due_soon is None:
            self._due_soon = int(await SettingsService(self.session).get("knowledge.due_soon_days"))
        return self._due_soon

    async def status_of(self, item: KnowledgeItem) -> str:
        return rules.review_status(item.next_review_on, today(), await self.due_soon_days(), status=item.status)

    async def names(self, ids: Iterable[UUID | None]) -> dict[UUID, str]:
        clean = {i for i in ids if i}
        if not clean:
            return {}
        return dict((await self.session.execute(select(User.id, User.full_name).where(User.id.in_(clean)))).all())

    async def summaries(self, items: Sequence[KnowledgeItem]) -> list[ItemSummaryOut]:
        tree = await self.tree()
        names = await self.names({i.owner_id for i in items})
        due_soon = await self.due_soon_days()
        return [
            ItemSummaryOut(
                id=i.id,
                title=i.title,
                kind=i.kind,
                kind_label=KIND_LABELS.get(i.kind, i.kind.title()),
                category_id=i.category_id,
                category_path=tree.path(i.category_id),
                owner_id=i.owner_id,
                owner_name=names.get(i.owner_id) if i.owner_id else None,
                version=i.version_label,
                status=rules.review_status(i.next_review_on, today(), due_soon, status=i.status),
                next_review_on=i.next_review_on,
                is_critical=i.is_critical,
                visibility=i.visibility,
                updated_at=i.updated_at,
            )
            for i in items
        ]

    async def summary(self, item: KnowledgeItem) -> ItemSummaryOut:
        return (await self.summaries([item]))[0]
