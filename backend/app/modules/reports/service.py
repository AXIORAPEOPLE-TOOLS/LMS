from collections.abc import Sequence
from datetime import timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, PermissionDeniedError, ValidationFailedError
from app.modules.audit.service import AuditService
from app.modules.identity.models import User
from app.modules.notifications.models import NotificationKind
from app.modules.notifications.service import NotificationService
from app.modules.reports import definitions  # noqa: F401  (registers the standard reports)
from app.modules.reports.base import GROUPS, REPORTS, Report, ReportContext, team_ids_for
from app.modules.reports.exporters import EXPORTERS
from app.modules.reports.models import ReportSchedule
from app.shared.clock import local_now, utcnow

FILTER_KEYS = {"period", "department", "skill", "programme", "days"}


class ReportService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _report(self, report_id: str, viewer: User) -> Report:
        report = REPORTS.get(report_id)
        if report is None:
            raise NotFoundError("We could not find that report.")
        if report.admin_only and not viewer.has_role("admin"):
            raise PermissionDeniedError("Only admins can run this report.")
        return report

    def catalogue(self, viewer: User) -> list[dict[str, Any]]:
        visible = [r for r in REPORTS.values() if not r.admin_only or viewer.has_role("admin")]
        return [
            {
                "group": group,
                "reports": [{"id": r.id, "name": r.name, "description": r.description} for r in visible if r.group == group],
            }
            for group in GROUPS
        ]

    async def _context(self, viewer: User, filters: dict[str, Any]) -> ReportContext:
        clean = {k: v for k, v in filters.items() if k in FILTER_KEYS and v not in (None, "", "all", "All")}
        return ReportContext(viewer=viewer, filters=clean, team_ids=await team_ids_for(self.session, viewer))

    async def run(self, report_id: str, viewer: User, filters: dict[str, Any]) -> dict[str, Any]:
        report = self._report(report_id, viewer)
        ctx = await self._context(viewer, filters)
        rows = await report.rows(self.session, ctx)
        return {
            "id": report.id,
            "name": report.name,
            "group": report.group,
            "description": report.description,
            "filters": report.filters,
            "columns": [c.__dict__ for c in report.columns],
            "rows": rows,
            "scope": "team" if ctx.team_ids is not None else "company",
        }

    async def drill(
        self, report_id: str, viewer: User, filters: dict[str, Any], row_key: str, column: str
    ) -> list[dict[str, Any]]:
        report = self._report(report_id, viewer)
        if not any(c.key == column and c.drill for c in report.columns):
            raise ValidationFailedError("This number has no list behind it.")
        rows = await report.drill(self.session, await self._context(viewer, filters), row_key, column)
        AuditService(self.session).record("report.drilldown", "report", report.id, actor_id=viewer.id, row=row_key, column=column)
        return rows

    async def export(self, report_id: str, viewer: User, filters: dict[str, Any], fmt: str) -> tuple[bytes, str, str]:
        exporter = EXPORTERS.get(fmt)
        if exporter is None:
            raise ValidationFailedError("Choose Excel, CSV or PDF.")
        report = self._report(report_id, viewer)
        ctx = await self._context(viewer, filters)
        rows = await report.rows(self.session, ctx)
        filter_text = ", ".join(f"{k}: {v}" for k, v in ctx.filters.items()) or "no filters"
        watermark = f"Exported by {viewer.full_name} on {local_now():%d %b %Y %H:%M} · {filter_text}"
        if report.has_personal_data:
            watermark += " · Contains personal data: do not share outside the company"
        content = exporter.export(report.name, report.columns, rows, watermark)
        AuditService(self.session).record(
            "report.exported",
            "report",
            report.id,
            actor_id=viewer.id,
            format=fmt,
            filters=ctx.filters,
            rows=len(rows),
            personal_data=report.has_personal_data,
        )
        filename = f"{report.id}-{local_now():%Y%m%d}.{exporter.extension}"
        return content, exporter.media_type, filename

    # ---- schedules ------------------------------------------------------------------------
    async def schedule(self, report_id: str, viewer: User, frequency: str, fmt: str, filters: dict[str, Any]) -> ReportSchedule:
        self._report(report_id, viewer)
        if frequency not in {"weekly", "monthly"} or fmt not in EXPORTERS:
            raise ValidationFailedError("Choose weekly or monthly, and Excel, CSV or PDF.")
        ctx = await self._context(viewer, filters)
        schedule = ReportSchedule(
            report_id=report_id, owner_id=viewer.id, frequency=frequency, export_format=fmt, filters=ctx.filters
        )
        self.session.add(schedule)
        await self.session.flush()
        AuditService(self.session).record("report.scheduled", "report", report_id, actor_id=viewer.id, frequency=frequency)
        return schedule

    async def schedules(self, viewer: User) -> Sequence[ReportSchedule]:
        return (
            await self.session.scalars(
                select(ReportSchedule).where(ReportSchedule.owner_id == viewer.id).order_by(ReportSchedule.created_at)
            )
        ).all()

    async def delete_schedule(self, schedule_id: UUID, viewer: User) -> None:
        schedule = await self.session.get(ReportSchedule, schedule_id)
        if schedule is None or schedule.owner_id != viewer.id:
            raise NotFoundError("We could not find that schedule.")
        await self.session.delete(schedule)

    async def send_due_schedules(self) -> int:
        """Weekly task: tell owners their scheduled report is ready (email attachment when email is live)."""
        sent = 0
        for schedule in (await self.session.scalars(select(ReportSchedule))).all():
            gap = timedelta(days=7 if schedule.frequency == "weekly" else 28)
            if schedule.last_sent_at and utcnow() - schedule.last_sent_at < gap - timedelta(hours=12):
                continue
            report = REPORTS.get(schedule.report_id)
            if report is None:
                continue
            schedule.last_sent_at = utcnow()
            query = "&".join(f"{k}={v}" for k, v in schedule.filters.items())
            await NotificationService(self.session).notify(
                schedule.owner_id,
                kind=NotificationKind.SUMMARY,
                title=f"Your {schedule.frequency} report: {report.name}",
                body="It is ready to download.",
                link=f"/admin/reports?report={report.id}&{query}".rstrip("&"),
                automatic=True,
            )
            sent += 1
        return sent
