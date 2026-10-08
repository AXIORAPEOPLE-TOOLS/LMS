"""Knowledge Hub reports, registered into the shared reports centre."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.knowledge.dashboard_service import DashboardService
from app.modules.knowledge.models import ItemStatus, KnowledgeItem
from app.modules.knowledge.presenter import Presenter
from app.modules.reports.base import Column, Report, ReportContext, register_report


@register_report
class KnowledgeHealthByFunction(Report):
    id, name, group = "knowledge_health", "Knowledge health by function", "Knowledge Hub"
    has_personal_data = False
    filters: list[str] = []
    columns = [Column("function", "Function"), Column("score", "Health", "number")]

    async def rows(self, session: AsyncSession, ctx: ReportContext) -> list[dict[str, Any]]:
        board = await DashboardService(session).leader()
        return [{"function": f.name, "score": f.score} for f in board.by_function]


@register_report
class KnowledgeReviewStatus(Report):
    id, name, group = "knowledge_review_status", "Knowledge items and review status", "Knowledge Hub"
    filters: list[str] = []
    columns = [
        Column("title", "Item"),
        Column("kind", "Kind"),
        Column("category", "Category"),
        Column("owner", "Owner"),
        Column("version", "Version"),
        Column("status", "Status"),
        Column("next_review", "Next review", "date"),
    ]

    async def rows(self, session: AsyncSession, ctx: ReportContext) -> list[dict[str, Any]]:
        items = (
            await session.scalars(
                select(KnowledgeItem)
                .where(KnowledgeItem.status != ItemStatus.ARCHIVED.value)
                .order_by(KnowledgeItem.next_review_on)
            )
        ).all()
        return [
            {
                "title": s.title,
                "kind": s.kind_label,
                "category": s.category_path,
                "owner": s.owner_name or "No owner",
                "version": s.version,
                "status": s.status.replace("_", " "),
                "next_review": s.next_review_on.isoformat() if s.next_review_on else None,
            }
            for s in await Presenter(session).summaries(items)
        ]
