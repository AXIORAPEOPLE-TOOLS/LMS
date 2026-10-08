"""Standard reports (sheet 13). Add one = one class with @register_report."""

from collections import defaultdict
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.assessments.models import SkillTest, TestAttempt, TestInvite
from app.modules.audit.models import AuditLog
from app.modules.certificates.models import Certificate
from app.modules.gamification.models import PointEntry
from app.modules.identity.models import Department, User
from app.modules.learning.models import Assignment, AssignmentStatus, Course, Invitation, LiveSession
from app.modules.notifications.models import Notification
from app.modules.pathways.models import STEP_ORDER, Pathway, PathwayItem, Step
from app.modules.reports.base import Column, Report, ReportContext, register_report
from app.modules.skills.models import JobRole, RoleSkill, Skill, SkillLevel
from app.modules.skills.rules import gap, stack_rank
from app.shared.clock import org_timezone, today


def _pct(part: int, whole: int) -> int:
    return round(part / whole * 100) if whole else 0


# ---- Skills and tests -----------------------------------------------------------------------
@register_report
class SkillLevelsByPerson(Report):
    id, name, group = "skill_levels", "Skill levels and gaps by person", "Skills and tests"
    description = "Every person, each required skill, their level and the gap."
    columns = [
        Column("person", "Person"),
        Column("department", "Department"),
        Column("role", "Role"),
        Column("skill", "Skill"),
        Column("level", "Level", "number"),
        Column("required", "Required", "number"),
        Column("gap", "Gap", "number"),
    ]
    filters = ["department"]

    async def rows(self, session: AsyncSession, ctx: ReportContext) -> list[dict[str, Any]]:
        stmt = (
            select(User.full_name, Department.name, JobRole.name, Skill.name, SkillLevel.level, RoleSkill.required_level)
            .join(JobRole, JobRole.id == User.job_role_id)
            .join(RoleSkill, RoleSkill.job_role_id == JobRole.id)
            .join(Skill, Skill.id == RoleSkill.skill_id)
            .outerjoin(Department, Department.id == User.department_id)
            .outerjoin(SkillLevel, (SkillLevel.user_id == User.id) & (SkillLevel.skill_id == Skill.id))
            .where(User.is_active.is_(True), ctx.scope_users(User.id))
            .order_by(User.full_name, Skill.name)
        )
        if ctx.filters.get("department"):
            stmt = stmt.where(Department.name == ctx.filters["department"])
        return [
            {"person": p, "department": d, "role": r, "skill": s, "level": lvl, "required": req, "gap": gap(req, lvl)}
            for p, d, r, s, lvl, req in (await session.execute(stmt)).all()
        ]


@register_report
class SkillRanking(Report):
    id, name, group = "skill_ranking", "Stack ranking by skill", "Skills and tests"
    columns = [
        Column("skill", "Skill"),
        Column("rank", "Rank", "number"),
        Column("person", "Person"),
        Column("score", "Score", "number"),
        Column("level", "Level", "number"),
    ]
    filters = ["skill"]

    async def rows(self, session: AsyncSession, ctx: ReportContext) -> list[dict[str, Any]]:
        stmt = (
            select(Skill.name, User.full_name, SkillLevel.score, SkillLevel.level, User.id)
            .join(SkillLevel, SkillLevel.skill_id == Skill.id)
            .join(User, User.id == SkillLevel.user_id)
            .where(SkillLevel.score.is_not(None), ctx.scope_users(User.id))
        )
        if ctx.filters.get("skill"):
            stmt = stmt.where(Skill.name == ctx.filters["skill"])
        by_skill: dict[str, list[tuple[Any, ...]]] = defaultdict(list)
        for skill, person, score, level, uid in (await session.execute(stmt)).all():
            by_skill[skill].append((uid, person, score, level))
        out: list[dict[str, Any]] = []
        for skill in sorted(by_skill):
            people = {uid: (person, level) for uid, person, _, level in by_skill[skill]}
            for entry in stack_rank((uid, score) for uid, _, score, _ in by_skill[skill]):
                person, level = people[entry.key]
                out.append({"skill": skill, "rank": entry.rank, "person": person, "score": int(entry.score), "level": level})
        return out


@register_report
class TestCompletion(Report):
    id, name, group = "test_completion", "Skill test completion", "Skills and tests"
    has_personal_data = False
    columns = [
        Column("test", "Test"),
        Column("invited", "Invited", "number"),
        Column("done", "Done", "number"),
        Column("done_pct", "Done %", "percent"),
        Column("avg_score", "Average score", "number"),
    ]

    async def rows(self, session: AsyncSession, ctx: ReportContext) -> list[dict[str, Any]]:
        invites = (
            await session.execute(
                select(SkillTest.title, func.count(), func.count().filter(TestInvite.status == "done"))
                .join(TestInvite, TestInvite.test_id == SkillTest.id)
                .where(ctx.scope_users(TestInvite.user_id))
                .group_by(SkillTest.title)
            )
        ).all()
        scores = dict(
            (
                await session.execute(
                    select(SkillTest.title, func.avg(TestAttempt.score))
                    .join(TestAttempt, TestAttempt.test_id == SkillTest.id)
                    .where(TestAttempt.score.is_not(None), ctx.scope_users(TestAttempt.user_id))
                    .group_by(SkillTest.title)
                )
            ).all()
        )
        return [
            {
                "test": t,
                "invited": i,
                "done": d,
                "done_pct": _pct(d, i),
                "avg_score": round(scores[t]) if scores.get(t) is not None else None,
            }
            for t, i, d in invites
        ]


# ---- Pathways and learning ----------------------------------------------------------------
@register_report
class CourseCompletion(Report):
    id, name, group = "course_completion", "Course completion", "Pathways and learning"
    has_personal_data = False
    columns = [
        Column("course", "Course"),
        Column("assigned", "Assigned", "number"),
        Column("completed", "Completed", "number"),
        Column("completed_pct", "Completed %", "percent"),
        Column("overdue", "Overdue", "number"),
    ]

    async def rows(self, session: AsyncSession, ctx: ReportContext) -> list[dict[str, Any]]:
        rows = (
            await session.execute(
                select(
                    Course.title,
                    func.count(),
                    func.count().filter(Assignment.status == AssignmentStatus.COMPLETED.value),
                    func.count().filter((Assignment.status != AssignmentStatus.COMPLETED.value) & (Assignment.due_on < today())),
                )
                .join(Assignment, Assignment.course_id == Course.id)
                .where(ctx.scope_users(Assignment.user_id))
                .group_by(Course.title)
                .order_by(Course.title)
            )
        ).all()
        return [{"course": c, "assigned": a, "completed": d, "completed_pct": _pct(d, a), "overdue": o} for c, a, d, o in rows]


@register_report
class PathwayProgress(Report):
    id, name, group = "pathway_progress", "Pathway progress by person", "Pathways and learning"
    columns = [
        Column("person", "Person"),
        Column("status", "Status"),
        Column("wave", "Current wave", "number"),
        Column("progress", "Progress %", "percent"),
    ]

    async def rows(self, session: AsyncSession, ctx: ReportContext) -> list[dict[str, Any]]:
        rows = (
            await session.execute(
                select(User.full_name, Pathway.status, PathwayItem.wave, PathwayItem.step)
                .join(Pathway, Pathway.user_id == User.id)
                .join(PathwayItem, PathwayItem.pathway_id == Pathway.id)
                .where(ctx.scope_users(User.id))
            )
        ).all()
        data: dict[tuple[str, str], list[tuple[int, str]]] = defaultdict(list)
        for person, status, wave, step in rows:
            data[(person, status)].append((wave, step))
        out = []
        for (person, status), items in sorted(data.items()):
            open_waves = [w for w, s in items if s != Step.DONE]
            done = sum(STEP_ORDER.index(Step(s)) for _, s in items)
            out.append(
                {
                    "person": person,
                    "status": status.replace("_", " "),
                    "wave": min(open_waves) if open_waves else None,
                    "progress": _pct(done, len(items) * (len(STEP_ORDER) - 1)),
                }
            )
        return out


@register_report
class LearningHours(Report):
    id, name, group = "learning_hours", "Learning hours by person", "Pathways and learning"
    columns = [
        Column("person", "Person"),
        Column("department", "Department"),
        Column("hours", "Hours", "number"),
        Column("lessons", "Lessons", "number"),
    ]

    async def rows(self, session: AsyncSession, ctx: ReportContext) -> list[dict[str, Any]]:
        rows = (
            await session.execute(
                select(
                    User.full_name,
                    Department.name,
                    func.sum(PointEntry.minutes),
                    func.count().filter(PointEntry.reason == "lesson"),
                )
                .join(PointEntry, PointEntry.user_id == User.id)
                .outerjoin(Department, Department.id == User.department_id)
                .where(PointEntry.at >= ctx.period_start_at, ctx.scope_users(User.id))
                .group_by(User.full_name, Department.name)
                .order_by(func.sum(PointEntry.minutes).desc())
            )
        ).all()
        return [{"person": p, "department": d, "hours": round((m or 0) / 60, 1), "lessons": n} for p, d, m, n in rows]


# ---- Compliance and certificates ------------------------------------------------------------
@register_report
class MandatoryCompliance(Report):
    id, name, group = "mandatory_compliance", "Mandatory training compliance", "Compliance and certificates"
    description = "By department. Click any number to see the people behind it."
    has_personal_data = False
    columns = [
        Column("department", "Department"),
        Column("assigned", "Assigned", "number", drill=True),
        Column("on_time", "On time", "number", drill=True),
        Column("overdue", "Overdue", "number", drill=True),
        Column("expired", "Expired", "number", drill=True),
        Column("on_time_pct", "On time %", "percent"),
    ]
    filters = ["period", "programme"]

    async def _data(self, session: AsyncSession, ctx: ReportContext) -> list[tuple[Any, ...]]:
        stmt = (
            select(
                Department.name,
                User.full_name,
                Course.title,
                Assignment.status,
                Assignment.due_on,
                Assignment.completed_at,
                Assignment.user_id,
                Assignment.course_id,
            )
            .join(User, User.id == Assignment.user_id)
            .join(Department, Department.id == User.department_id)
            .join(Course, Course.id == Assignment.course_id)
            .where(Assignment.is_mandatory.is_(True), ctx.scope_users(User.id))
        )
        if ctx.filters.get("programme"):
            stmt = stmt.where(Course.title == ctx.filters["programme"])
        return list((await session.execute(stmt)).all())

    def _bucket(self, row: tuple[Any, ...], expired: set[tuple[Any, Any]]) -> str:
        _, _, _, status, due, completed, user_id, course_id = row
        if (user_id, course_id) in expired:
            return "expired"
        if status == AssignmentStatus.COMPLETED.value:
            done_day = completed.astimezone(org_timezone()).date() if completed else None
            return "on_time" if (due is None or (done_day and done_day <= due)) else "late"
        if due and due < today():
            return "overdue"
        return "open"

    async def _expired(self, session: AsyncSession) -> set[tuple[Any, Any]]:
        return set(
            (
                await session.execute(
                    select(Certificate.user_id, Certificate.course_id).where(
                        Certificate.valid_until < today(), Certificate.status == "valid"
                    )
                )
            ).all()
        )

    async def rows(self, session: AsyncSession, ctx: ReportContext) -> list[dict[str, Any]]:
        expired = await self._expired(session)
        stats: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for row in await self._data(session, ctx):
            bucket = self._bucket(row, expired)
            stats[row[0]]["assigned"] += 1
            stats[row[0]][bucket] += 1
        return sorted(
            (
                {
                    "department": dept,
                    "assigned": s["assigned"],
                    "on_time": s["on_time"],
                    "overdue": s["overdue"],
                    "expired": s["expired"],
                    "on_time_pct": _pct(s["on_time"], s["assigned"] - s["open"]),
                }
                for dept, s in stats.items()
            ),
            key=lambda r: -r["on_time_pct"],
        )

    async def drill(self, session: AsyncSession, ctx: ReportContext, row_key: str, column: str) -> list[dict[str, Any]]:
        expired = await self._expired(session)
        out = []
        for row in await self._data(session, ctx):
            if row[0] != row_key:
                continue
            bucket = self._bucket(row, expired)
            if column == "assigned" or bucket == column:
                out.append(
                    {
                        "person": row[1],
                        "course": row[2],
                        "due_on": row[4].isoformat() if row[4] else None,
                        "status": bucket.replace("_", " "),
                    }
                )
        return out


@register_report
class CertificatesExpiring(Report):
    id, name, group = "certificates_expiring", "Certificates ending soon", "Compliance and certificates"
    columns = [
        Column("person", "Person"),
        Column("certificate", "Certificate"),
        Column("code", "ID"),
        Column("valid_until", "Valid until", "date"),
        Column("days_left", "Days left", "number"),
    ]

    async def rows(self, session: AsyncSession, ctx: ReportContext) -> list[dict[str, Any]]:
        horizon = today() + timedelta(days=int(ctx.filters.get("days", 60)))
        rows = (
            await session.execute(
                select(User.full_name, Certificate.title, Certificate.code, Certificate.valid_until)
                .join(User, User.id == Certificate.user_id)
                .where(
                    Certificate.status == "valid",
                    Certificate.valid_until.is_not(None),
                    Certificate.valid_until <= horizon,
                    ctx.scope_users(User.id),
                )
                .order_by(Certificate.valid_until)
            )
        ).all()
        return [
            {"person": p, "certificate": t, "code": c, "valid_until": v.isoformat(), "days_left": (v - today()).days}
            for p, t, c, v in rows
        ]


# ---- Sessions and reminders ---------------------------------------------------------------
@register_report
class SessionAttendance(Report):
    id, name, group = "session_replies", "Session invitations and replies", "Sessions and reminders"
    has_personal_data = False
    columns = [
        Column("session", "Session"),
        Column("starts", "Starts", "date"),
        Column("invited", "Invited", "number"),
        Column("accepted", "Accepted", "number"),
        Column("declined", "Declined", "number"),
        Column("waiting", "Waiting", "number"),
    ]

    async def rows(self, session: AsyncSession, ctx: ReportContext) -> list[dict[str, Any]]:
        rows = (
            await session.execute(
                select(
                    LiveSession.title,
                    LiveSession.starts_at,
                    func.count(),
                    func.count().filter(Invitation.status == "accepted"),
                    func.count().filter(Invitation.status == "declined"),
                    func.count().filter(Invitation.status == "pending"),
                )
                .join(Invitation, Invitation.session_id == LiveSession.id)
                .group_by(LiveSession.title, LiveSession.starts_at)
                .order_by(LiveSession.starts_at.desc())
            )
        ).all()
        return [
            {
                "session": t,
                "starts": s.astimezone(org_timezone()).strftime("%d %b %Y %H:%M"),
                "invited": i,
                "accepted": a,
                "declined": d,
                "waiting": w,
            }
            for t, s, i, a, d, w in rows
        ]


@register_report
class RemindersSent(Report):
    id, name, group = "reminders_sent", "Reminders sent by day", "Sessions and reminders"
    has_personal_data = False
    columns = [
        Column("day", "Day", "date"),
        Column("reminders", "Reminders", "number"),
        Column("invitations", "Invitations", "number"),
        Column("nudges", "Manager nudges", "number"),
    ]

    async def rows(self, session: AsyncSession, ctx: ReportContext) -> list[dict[str, Any]]:
        notes = (
            await session.execute(
                select(Notification.created_at, Notification.kind).where(
                    Notification.kind.in_(["reminder", "invitation", "nudge"]), Notification.created_at >= ctx.period_start_at
                )
            )
        ).all()
        days: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for created, kind in notes:
            days[created.astimezone(org_timezone()).date().isoformat()][kind] += 1
        return [
            {"day": d, "reminders": v["reminder"], "invitations": v["invitation"], "nudges": v["nudge"]}
            for d, v in sorted(days.items(), reverse=True)
        ]


# ---- Gamification and careers -----------------------------------------------------------------
@register_report
class PointsLeaders(Report):
    id, name, group = "points", "Points by person", "Gamification and careers"
    columns = [Column("person", "Person"), Column("points", "Points", "number"), Column("badges_entries", "Activities", "number")]

    async def rows(self, session: AsyncSession, ctx: ReportContext) -> list[dict[str, Any]]:
        rows = (
            await session.execute(
                select(User.full_name, func.sum(PointEntry.points), func.count())
                .join(PointEntry, PointEntry.user_id == User.id)
                .where(PointEntry.at >= ctx.period_start_at, ctx.scope_users(User.id))
                .group_by(User.full_name)
                .order_by(func.sum(PointEntry.points).desc())
            )
        ).all()
        return [{"person": p, "points": int(s or 0), "badges_entries": n} for p, s, n in rows]


# ---- Audit and impact -------------------------------------------------------------------------
@register_report
class LevelGains(Report):
    id, name, group = "level_gains", "Level gains (impact)", "Audit and impact"
    columns = [
        Column("person", "Person"),
        Column("skill", "Skill"),
        Column("from_level", "From", "number"),
        Column("to_level", "To", "number"),
        Column("source", "How"),
    ]

    async def rows(self, session: AsyncSession, ctx: ReportContext) -> list[dict[str, Any]]:
        rows = (
            await session.execute(
                select(User.full_name, Skill.name, SkillLevel.previous_level, SkillLevel.level, SkillLevel.source)
                .join(User, User.id == SkillLevel.user_id)
                .join(Skill, Skill.id == SkillLevel.skill_id)
                .where(
                    SkillLevel.previous_level.is_not(None), SkillLevel.level > SkillLevel.previous_level, ctx.scope_users(User.id)
                )
                .order_by(User.full_name)
            )
        ).all()
        return [{"person": p, "skill": s, "from_level": f, "to_level": t, "source": src} for p, s, f, t, src in rows]


@register_report
class AuditTrail(Report):
    id, name, group = "audit_log", "Audit log", "Audit and impact"
    admin_only = True
    columns = [
        Column("at", "When", "date"),
        Column("actor", "Who"),
        Column("action", "Action"),
        Column("entity", "What"),
        Column("details", "Details"),
    ]

    async def rows(self, session: AsyncSession, ctx: ReportContext) -> list[dict[str, Any]]:
        rows = (
            await session.execute(
                select(AuditLog, User.full_name)
                .outerjoin(User, User.id == AuditLog.actor_id)
                .where(AuditLog.at >= ctx.period_start_at)
                .order_by(AuditLog.at.desc())
                .limit(5000)
            )
        ).all()
        return [
            {
                "at": log.at.astimezone(org_timezone()).strftime("%Y-%m-%d %H:%M"),
                "actor": name or "System",
                "action": log.action,
                "entity": f"{log.entity_type} {log.entity_id or ''}".strip(),
                "details": ", ".join(f"{k}={v}" for k, v in (log.details or {}).items())[:300],
            }
            for log, name in rows
        ]
