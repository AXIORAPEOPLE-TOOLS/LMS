"""Report contract + registry. Each report is a small class (SRP); the centre lists whatever is registered."""

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any, ClassVar
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.models import User
from app.shared.clock import org_timezone, today

GROUPS = [
    "Skills and tests",
    "Pathways and learning",
    "Compliance and certificates",
    "Sessions and reminders",
    "Gamification and careers",
    "Knowledge Hub",
    "Audit and impact",
]


@dataclass(frozen=True)
class Column:
    key: str
    label: str
    kind: str = "text"  # text | number | percent | date
    drill: bool = False  # click the number to see the people behind it


@dataclass
class ReportContext:
    viewer: User
    filters: dict[str, Any] = field(default_factory=dict)
    team_ids: list[UUID] | None = None  # managers see only their own team

    @property
    def period_start(self) -> date:
        days = {"week": 7, "month": 30, "quarter": 91, "year": 365}.get(self.filters.get("period", "quarter"), 91)
        return today() - timedelta(days=days)

    @property
    def period_start_at(self) -> datetime:
        """Start of the period as a timestamp (local midnight), for datetime columns."""
        return datetime.combine(self.period_start, time(0), tzinfo=org_timezone())

    def scope_users(self, column: Any) -> Any:
        """Add `WHERE user in team` for managers (no-op for admins)."""
        return column.in_(self.team_ids) if self.team_ids is not None else True


class Report:
    id: ClassVar[str]
    name: ClassVar[str]
    group: ClassVar[str]
    description: ClassVar[str] = ""
    columns: ClassVar[list[Column]]
    filters: ClassVar[list[str]] = ["period"]
    has_personal_data: ClassVar[bool] = True
    admin_only: ClassVar[bool] = False

    async def rows(self, session: AsyncSession, ctx: ReportContext) -> list[dict[str, Any]]:
        raise NotImplementedError

    async def drill(self, session: AsyncSession, ctx: ReportContext, row_key: str, column: str) -> list[dict[str, Any]]:
        return []


REPORTS: dict[str, Report] = {}


def register_report(report_cls: type[Report]) -> type[Report]:
    REPORTS[report_cls.id] = report_cls()
    return report_cls


async def team_ids_for(session: AsyncSession, viewer: User) -> list[UUID] | None:
    if viewer.has_role("admin"):
        return None
    return list((await session.scalars(select(User.id).where(User.manager_id == viewer.id))).all())
