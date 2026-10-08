"""Leader dashboard (K-11) and function dashboard (K-12). Click any number to see the list behind it."""

from collections import defaultdict
from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.modules.knowledge import rules
from app.modules.knowledge.library_service import LibraryService
from app.modules.knowledge.models import ItemStatus, KnowledgeAccessRequest, KnowledgeHealthSnapshot, KnowledgeItem
from app.modules.knowledge.presenter import Presenter
from app.modules.knowledge.schemas import (
    AttentionOut,
    CategoryHealthOut,
    FunctionDashboardOut,
    FunctionHealthOut,
    HealthTileOut,
    LeaderDashboardOut,
    OwnerHealthOut,
)
from app.modules.settings.service import SettingsService
from app.shared.clock import today, utcnow

TARGET_ON_TIME = 90


class DashboardService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.presenter = Presenter(session)

    async def _live_items(self) -> list[KnowledgeItem]:
        return list(
            (await self.session.scalars(select(KnowledgeItem).where(KnowledgeItem.status != ItemStatus.ARCHIVED.value))).all()
        )

    async def _tile(self, items: list[KnowledgeItem]) -> HealthTileOut:
        weights = await SettingsService(self.session).get("knowledge.health_weights")
        statuses = [(await self.presenter.status_of(i), bool(i.owner_id), bool(i.backup_owner_id)) for i in items]
        h = rules.health(statuses, weights)
        return HealthTileOut(
            score=h.score,
            items=h.items,
            on_time_pct=h.on_time_pct,
            overdue=h.overdue,
            due_soon=h.due_soon,
            no_owner=h.no_owner,
            no_backup=h.no_backup,
            critical=sum(1 for i in items if i.is_critical),
        )

    async def leader(self) -> LeaderDashboardOut:
        items = await self._live_items()
        tree = await self.presenter.tree()
        by_root: dict[UUID, list[KnowledgeItem]] = defaultdict(list)
        for item in items:
            root = tree.root_of(item.category_id)
            if root:
                by_root[root].append(item)
        functions = [
            FunctionHealthOut(category_id=root, name=tree.by_id[root].name, score=(await self._tile(group)).score)
            for root, group in by_root.items()
        ]
        functions.sort(key=lambda f: -f.score)
        company = await self._tile(items)
        trend = await self._trend(None, company.score)
        previous = trend[-2]["score"] if len(trend) >= 2 else None
        return LeaderDashboardOut(
            company=company,
            change_since_last_month=company.score - previous if previous is not None else None,
            functions_count=len(functions),
            trend=trend,
            by_function=functions,
            attention=await self._attention(items, by_root, tree),
            target_on_time_pct=TARGET_ON_TIME,
        )

    async def _attention(self, items: list[KnowledgeItem], by_root: dict[UUID, list[KnowledgeItem]], tree) -> list[AttentionOut]:  # type: ignore[no-untyped-def]
        out: list[AttentionOut] = []
        overdue_by_root: dict[UUID, int] = {}
        for root, group in by_root.items():
            overdue_by_root[root] = sum([1 for i in group if await self.presenter.status_of(i) == "overdue"])
        if overdue_by_root and max(overdue_by_root.values()) > 0:
            worst = max(overdue_by_root, key=lambda r: overdue_by_root[r])
            out.append(
                AttentionOut(
                    text=f"{tree.by_id[worst].name}: {overdue_by_root[worst]} items overdue (most of any function)",
                    action="Open list",
                    href=f"/knowledge/library?category={worst}&status=overdue",
                )
            )
        success = await LibraryService(self.session).search_success()
        weak = []
        for root in by_root:
            total = found = 0
            for cid, (t, f) in success.items():
                if cid and tree.root_of(cid) == root:
                    total, found = total + t, found + f
            if total >= 5 and found / total < 0.4:
                weak.append(tree.by_id[root].name)
        if weak:
            out.append(
                AttentionOut(
                    text=f"{' and '.join(weak)}: search success below 40%", action="See topics", href="/knowledge/dashboard"
                )
            )
        no_owner = sum(1 for i in items if not i.owner_id)
        if no_owner:
            out.append(
                AttentionOut(
                    text=f"{no_owner} item{'s have' if no_owner != 1 else ' has'} no owner",
                    action="Assign",
                    href="/knowledge/admin/access",
                )
            )
        waiting = (
            await self.session.scalars(select(KnowledgeAccessRequest).where(KnowledgeAccessRequest.status == "pending"))
        ).all()
        old = [r for r in waiting if (utcnow() - r.created_at).days >= 2]
        if old:
            out.append(
                AttentionOut(
                    text=f"{len(old)} access requests waiting more than 2 days", action="Review", href="/knowledge/admin/access"
                )
            )
        return out

    async def _trend(self, category_id: UUID | None, current: int) -> list[dict[str, object]]:
        await self.snapshot_month(category_id, current)
        stmt = (
            select(KnowledgeHealthSnapshot)
            .where(
                KnowledgeHealthSnapshot.category_id == category_id
                if category_id
                else KnowledgeHealthSnapshot.category_id.is_(None)
            )
            .order_by(KnowledgeHealthSnapshot.month)
        )
        rows = (await self.session.scalars(stmt)).all()
        return [{"month": date.fromisoformat(r.month + "-01").strftime("%b"), "score": r.score} for r in rows[-6:]]

    async def snapshot_month(self, category_id: UUID | None, score: int) -> None:
        month = today().strftime("%Y-%m")
        existing = (
            await self.session.scalars(
                select(KnowledgeHealthSnapshot).where(
                    KnowledgeHealthSnapshot.month == month,
                    KnowledgeHealthSnapshot.category_id == category_id
                    if category_id
                    else KnowledgeHealthSnapshot.category_id.is_(None),
                )
            )
        ).first()
        if existing:
            existing.score = score
        else:
            self.session.add(KnowledgeHealthSnapshot(month=month, category_id=category_id, score=score))
        await self.session.flush()

    async def function(self, category_id: UUID) -> FunctionDashboardOut:
        tree = await self.presenter.tree()
        root = tree.by_id.get(category_id)
        if root is None:
            raise NotFoundError("We could not find that function.")
        ids = tree.descendants(category_id)
        items = [i for i in await self._live_items() if i.category_id in ids]
        tile = await self._tile(items)
        statuses = {i.id: await self.presenter.status_of(i) for i in items}
        by_category: list[CategoryHealthOut] = []
        for child in sorted((c for c in tree.by_id.values() if c.parent_id == category_id), key=lambda c: (c.position, c.name)):
            child_ids = tree.descendants(child.id)
            group = [i for i in items if i.category_id in child_ids]
            overdue = sum(1 for i in group if statuses[i.id] == "overdue")
            by_category.append(
                CategoryHealthOut(
                    category_id=child.id,
                    name=child.name,
                    items=len(group),
                    overdue=overdue,
                    ok_pct=round((len(group) - overdue) / len(group) * 100) if group else 100,
                )
            )
        owners: dict[UUID, list[KnowledgeItem]] = defaultdict(list)
        for item in items:
            if item.owner_id:
                owners[item.owner_id].append(item)
        names = await self.presenter.names(set(owners))
        by_owner = sorted(
            (
                OwnerHealthOut(
                    owner_id=o,
                    name=names.get(o, "Owner"),
                    items=len(group),
                    overdue=sum(1 for i in group if statuses[i.id] == "overdue"),
                )
                for o, group in owners.items()
            ),
            key=lambda r: (-r.overdue, -r.items),
        )
        await self.snapshot_month(category_id, tile.score)
        return FunctionDashboardOut(
            category_id=category_id,
            name=root.name,
            tile=tile,
            by_category=by_category,
            by_owner=by_owner,
            overdue_owner_count=sum(1 for o in by_owner if o.overdue),
            items_without_backup=tile.no_backup,
        )
