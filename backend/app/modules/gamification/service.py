"""Points, levels, badges, challenges (L-09) and live leaderboards (L-08)."""

import hashlib
import json
from collections import defaultdict
from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, ValidationFailedError
from app.modules.audit.service import AuditService
from app.modules.certificates.models import Certificate
from app.modules.gamification import rules
from app.modules.gamification.models import (
    Badge,
    Challenge,
    ChallengeMember,
    LeaderboardSnapshot,
    PointEntry,
    UserBadge,
)
from app.modules.gamification.schemas import (
    BadgeOut,
    BadgesOut,
    BoardOut,
    BoardRowOut,
    ChallengeIn,
    ChallengeOut,
    ComplianceBoardOut,
    DepartmentRateOut,
    ProfileOut,
)
from app.modules.identity.models import Department, User
from app.modules.learning.models import Assignment, AssignmentStatus, Course
from app.modules.pathways.models import STEP_ORDER, Pathway, PathwayItem, Step
from app.modules.settings.service import SettingsService
from app.modules.skills.models import Skill, SkillLevel
from app.modules.skills.service import short_name
from app.shared.clock import org_timezone, today, utcnow

BOARDS = {
    "skill_champions": "Skill champions",
    "learning_hours": "Learning hours",
    "pathway_progress": "Pathway progress",
    "most_improved": "Most improved",
}
PERIOD_DAYS = {"week": 7, "month": 30, "quarter": 91}


class GamificationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.settings = SettingsService(session)

    # ---- points & badges ------------------------------------------------------------
    async def award(self, user_id: UUID, reason: str, ref_id: UUID | None, *, minutes: int = 0, points: int | None = None) -> int:
        """Give points once per (user, reason, thing). Returns points given (0 if already given)."""
        if points is None:
            points = int((await self.settings.get("gamification.points")).get(reason, 0))
        if points <= 0 and minutes <= 0:
            return 0
        existing = (
            await self.session.scalars(
                select(PointEntry.id).where(
                    PointEntry.user_id == user_id, PointEntry.reason == reason, PointEntry.ref_id == ref_id
                )
            )
        ).first()
        if existing:
            return 0
        try:
            async with self.session.begin_nested():
                self.session.add(
                    PointEntry(user_id=user_id, points=max(0, points), reason=reason, ref_id=ref_id, minutes=minutes)
                )
        except IntegrityError:
            return 0
        await self.evaluate_badges(user_id)
        return points

    async def total_points(self, user_id: UUID) -> int:
        return int(
            await self.session.scalar(select(func.coalesce(func.sum(PointEntry.points), 0)).where(PointEntry.user_id == user_id))
            or 0
        )

    async def activity_days(self, user_id: UUID) -> set[date]:
        stamps = (
            await self.session.scalars(
                select(PointEntry.at).where(PointEntry.user_id == user_id, PointEntry.at >= utcnow() - timedelta(days=120))
            )
        ).all()
        tz = org_timezone()
        return {s.astimezone(tz).date() for s in stamps}

    async def evaluate_badges(self, user_id: UUID) -> list[str]:
        earned = set((await self.session.scalars(select(UserBadge.badge_id).where(UserBadge.user_id == user_id))).all())
        new: list[str] = []
        for badge in (await self.session.scalars(select(Badge))).all():
            if badge.id in earned:
                continue
            if await self._meets(user_id, badge.rule):
                self.session.add(UserBadge(user_id=user_id, badge_id=badge.id))
                new.append(badge.code)
        if new:
            await self.session.flush()
        return new

    async def _meets(self, user_id: UUID, rule: dict) -> bool:  # type: ignore[type-arg]
        kind = rule.get("type")
        if kind == "count":
            count = await self.session.scalar(
                select(func.count()).where(PointEntry.user_id == user_id, PointEntry.reason == rule["reason"])
            )
            return int(count or 0) >= int(rule.get("at_least", 1))
        if kind == "points":
            return await self.total_points(user_id) >= int(rule["at_least"])
        if kind == "streak":
            return rules.streak_days(await self.activity_days(user_id), today()) >= int(rule["days"])
        if kind == "certificate_title":
            count = await self.session.scalar(
                select(func.count()).where(Certificate.user_id == user_id, Certificate.title.ilike(f"%{rule['contains']}%"))
            )
            return int(count or 0) > 0
        if kind == "max_level":
            level = await self.session.scalar(select(func.max(SkillLevel.level)).where(SkillLevel.user_id == user_id))
            return int(level or 0) >= int(rule["at_least"])
        return False

    async def profile(self, user: User) -> ProfileOut:
        points = await self.total_points(user.id)
        level = rules.profile_level(points, await self.settings.get("gamification.levels"))
        week_start = utcnow() - timedelta(days=7)
        week = (
            await self.session.execute(
                select(PointEntry.reason, func.count(), func.sum(PointEntry.points))
                .where(PointEntry.user_id == user.id, PointEntry.at >= week_start)
                .group_by(PointEntry.reason)
            )
        ).all()
        by_reason = {r: (int(c), int(p or 0)) for r, c, p in week}
        levels_gained = int(
            await self.session.scalar(select(func.count()).where(PointEntry.user_id == user.id, PointEntry.reason == "level_up"))
            or 0
        )
        certificates = int(
            await self.session.scalar(select(func.count()).where(Certificate.user_id == user.id, Certificate.status == "valid"))
            or 0
        )
        top_level = await self.session.scalar(select(func.max(SkillLevel.level)).where(SkillLevel.user_id == user.id))
        names = await self.settings.get("skills.level_names")
        return ProfileOut(
            user_id=user.id,
            full_name=user.full_name,
            initials=user.display_initials,
            skill_level_name=f"{names[top_level]} · Level {top_level}" if top_level is not None else None,
            points=points,
            level_number=level.number,
            level_name=level.name,
            next_level_name=level.next_name,
            points_to_next=level.points_to_next,
            level_progress_pct=level.progress_pct,
            streak_days=rules.streak_days(await self.activity_days(user.id), today()),
            levels_gained=levels_gained,
            certificates=certificates,
            week_points=sum(p for _, p in by_reason.values()),
            week_lessons=by_reason.get("lesson", (0, 0))[0],
            week_tests=by_reason.get("test", (0, 0))[0],
            show_name_on_boards=user.show_name_on_boards,
        )

    async def badges(self, user: User) -> BadgesOut:
        mine = dict(
            (
                await self.session.execute(select(UserBadge.badge_id, UserBadge.awarded_at).where(UserBadge.user_id == user.id))
            ).all()
        )
        badges = (await self.session.scalars(select(Badge).order_by(Badge.position, Badge.name))).all()
        out = [
            BadgeOut(code=b.code, name=b.name, description=b.description, earned=b.id in mine, awarded_at=mine.get(b.id))
            for b in badges
        ]
        out.sort(key=lambda b: not b.earned)
        return BadgesOut(earned=len(mine), total=len(badges), badges=out)

    # ---- challenges -------------------------------------------------------------------
    async def create_challenge(self, data: ChallengeIn, actor: User) -> Challenge:
        if data.ends_on < data.starts_on:
            raise ValidationFailedError("The challenge must end after it starts.")
        challenge = Challenge(**data.model_dump(), created_by_id=actor.id)
        self.session.add(challenge)
        await self.session.flush()
        AuditService(self.session).record("challenge.created", "challenge", challenge.id, actor_id=actor.id)
        return challenge

    async def challenges_for(self, user: User) -> list[ChallengeOut]:
        stmt = select(Challenge).where(Challenge.ends_on >= today() - timedelta(days=7)).order_by(Challenge.ends_on)
        out: list[ChallengeOut] = []
        for challenge in (await self.session.scalars(stmt)).all():
            if challenge.department_id and challenge.department_id != user.department_id:
                continue
            out.append(await self._challenge_out(challenge, user))
        return out

    async def _team(self, challenge: Challenge) -> list[UUID]:
        members = list(
            (
                await self.session.scalars(select(ChallengeMember.user_id).where(ChallengeMember.challenge_id == challenge.id))
            ).all()
        )
        if challenge.department_id:
            dept_people = list(
                (
                    await self.session.scalars(
                        select(User.id).where(User.department_id == challenge.department_id, User.is_active.is_(True))
                    )
                ).all()
            )
            return dept_people or members
        return members

    async def team_progress(self, challenge: Challenge) -> int:
        team = await self._team(challenge)
        if not team:
            return 0
        total, done = (
            await self.session.execute(
                select(func.count(), func.count().filter(Assignment.status == AssignmentStatus.COMPLETED.value)).where(
                    Assignment.user_id.in_(team)
                )
            )
        ).one()
        return round(done / total * 100) if total else 0

    async def _challenge_out(self, challenge: Challenge, user: User) -> ChallengeOut:
        joined = bool(
            (
                await self.session.scalars(
                    select(ChallengeMember.id).where(
                        ChallengeMember.challenge_id == challenge.id, ChallengeMember.user_id == user.id
                    )
                )
            ).first()
        )
        members = int(await self.session.scalar(select(func.count()).where(ChallengeMember.challenge_id == challenge.id)) or 0)
        my_open = (
            await self.session.execute(
                select(Course.title, Course.duration_minutes)
                .join(Assignment, Assignment.course_id == Course.id)
                .where(Assignment.user_id == user.id, Assignment.status != AssignmentStatus.COMPLETED.value)
                .order_by(Assignment.due_on.is_(None), Assignment.due_on)
                .limit(3)
            )
        ).all()
        return ChallengeOut(
            id=challenge.id,
            title=challenge.title,
            description=challenge.description,
            goal_pct=challenge.goal_pct,
            team_pct=await self.team_progress(challenge),
            days_left=max(0, (challenge.ends_on - today()).days),
            ends_on=challenge.ends_on,
            reward_points=challenge.reward_points,
            reward_badge_code=challenge.reward_badge_code,
            status=challenge.status,
            joined=joined,
            members=members,
            my_part=[f'Finish "{t}" ({m} min)' for t, m in my_open],
        )

    async def join(self, challenge_id: UUID, user: User) -> ChallengeOut:
        challenge = await self.session.get(Challenge, challenge_id)
        if challenge is None:
            raise NotFoundError("We could not find that challenge.")
        exists = (
            await self.session.scalars(
                select(ChallengeMember.id).where(ChallengeMember.challenge_id == challenge.id, ChallengeMember.user_id == user.id)
            )
        ).first()
        if not exists:
            self.session.add(ChallengeMember(challenge_id=challenge.id, user_id=user.id))
            await self.session.flush()
        return await self._challenge_out(challenge, user)

    async def settle_challenges(self) -> int:
        """Daily: reward teams that reached the goal; close ended challenges."""
        settled = 0
        for challenge in (await self.session.scalars(select(Challenge).where(Challenge.status == "active"))).all():
            pct = await self.team_progress(challenge)
            if pct >= challenge.goal_pct:
                challenge.status = "won"
                members = (
                    await self.session.scalars(
                        select(ChallengeMember.user_id).where(ChallengeMember.challenge_id == challenge.id)
                    )
                ).all()
                badge = (
                    (await self.session.scalars(select(Badge).where(Badge.code == challenge.reward_badge_code))).first()
                    if challenge.reward_badge_code
                    else None
                )
                for user_id in members:
                    await self.award(user_id, "challenge", challenge.id, points=challenge.reward_points)
                    if badge:
                        has = (
                            await self.session.scalars(
                                select(UserBadge.id).where(UserBadge.user_id == user_id, UserBadge.badge_id == badge.id)
                            )
                        ).first()
                        if not has:
                            self.session.add(UserBadge(user_id=user_id, badge_id=badge.id))
                settled += 1
            elif challenge.ends_on < today():
                challenge.status = "ended"
                settled += 1
        return settled

    # ---- leaderboards -------------------------------------------------------------------
    async def board(
        self, board: str, viewer: User, *, scope: str = "company", period: str = "quarter", skill_id: UUID | None = None
    ) -> BoardOut:
        if board not in BOARDS:
            raise ValidationFailedError("Unknown leaderboard.")
        since = utcnow() - timedelta(days=PERIOD_DAYS.get(period, 91))
        people_stmt = select(User).where(User.is_active.is_(True))
        if scope == "team" and viewer.department_id:
            people_stmt = people_stmt.where(User.department_id == viewer.department_id)
        people = {u.id: u for u in (await self.session.scalars(people_stmt)).all()}
        values: dict[UUID, float] = {}
        title = BOARDS[board]
        if board == "skill_champions":
            if skill_id is None:
                skill_id = await self._default_skill(viewer)
            if skill_id:
                skill = await self.session.get(Skill, skill_id)
                title = f"Skill champions: {skill.name}" if skill else title
                for sl in (
                    await self.session.scalars(
                        select(SkillLevel).where(SkillLevel.skill_id == skill_id, SkillLevel.score.is_not(None))
                    )
                ).all():
                    values[sl.user_id] = float(sl.score or 0)
        elif board == "learning_hours":
            rows = (
                await self.session.execute(
                    select(PointEntry.user_id, func.sum(PointEntry.minutes))
                    .where(PointEntry.at >= since)
                    .group_by(PointEntry.user_id)
                )
            ).all()
            values = {u: round(float(m or 0) / 60, 1) for u, m in rows if m}
        elif board == "pathway_progress":
            items = (
                await self.session.execute(
                    select(Pathway.user_id, PathwayItem.step)
                    .join(PathwayItem, PathwayItem.pathway_id == Pathway.id)
                    .where(Pathway.status != "completed")
                )
            ).all()
            steps: dict[UUID, list[int]] = defaultdict(list)
            for user_id, step in items:
                steps[user_id].append(STEP_ORDER.index(Step(step)))
            values = {u: round(sum(s) / (len(s) * (len(STEP_ORDER) - 1)) * 100) for u, s in steps.items() if s}
        elif board == "most_improved":
            rows = (
                await self.session.execute(
                    select(PointEntry.user_id, func.count())
                    .where(PointEntry.reason == "level_up", PointEntry.at >= since)
                    .group_by(PointEntry.user_id)
                )
            ).all()
            values = {u: float(c) for u, c in rows}
        values = {u: v for u, v in values.items() if u in people}
        key = f"{board}|{scope}|{viewer.department_id if scope == 'team' else ''}|{skill_id or ''}"
        previous = await self._snapshot(key)
        departments = {d.id: d.name for d in (await self.session.scalars(select(Department))).all()}
        from app.modules.skills.rules import stack_rank

        rows_out: list[BoardRowOut] = []
        for entry in stack_rank(values.items()):
            person = people[entry.key]
            hidden = not person.show_name_on_boards and person.id != viewer.id
            name = "You" if person.id == viewer.id else ("A colleague" if hidden else short_name(person.full_name))
            if person.id == viewer.id:
                name = f"You ({short_name(person.full_name)})"
            before = previous.get(str(person.id)) if previous else None
            rows_out.append(
                BoardRowOut(
                    rank=entry.rank,
                    user_id=None if hidden else person.id,
                    name=name,
                    department=departments.get(person.department_id) if person.department_id else None,
                    value=entry.score,
                    display=_display(board, entry.score),
                    change=(before - entry.rank) if before else None,
                    is_me=person.id == viewer.id,
                )
            )
        version = hashlib.sha1(json.dumps([(r.rank, r.name, r.value) for r in rows_out]).encode()).hexdigest()[:12]
        return BoardOut(board=board, title=title, scope=scope, period=period, rows=rows_out, version=version)

    async def _default_skill(self, viewer: User) -> UUID | None:
        mine = (
            await self.session.scalars(
                select(SkillLevel.skill_id).where(SkillLevel.user_id == viewer.id, SkillLevel.score.is_not(None)).limit(1)
            )
        ).first()
        if mine:
            return mine
        return (await self.session.scalars(select(SkillLevel.skill_id).where(SkillLevel.score.is_not(None)).limit(1))).first()

    async def _snapshot(self, key: str) -> dict[str, int] | None:
        snap = (
            await self.session.scalars(
                select(LeaderboardSnapshot)
                .where(LeaderboardSnapshot.key == key)
                .order_by(LeaderboardSnapshot.taken_at.desc())
                .limit(1)
            )
        ).first()
        return snap.ranks if snap else None

    async def take_snapshot(self, board: BoardOut, key: str) -> None:
        self.session.add(LeaderboardSnapshot(key=key, ranks={str(r.user_id): r.rank for r in board.rows if r.user_id}))

    async def compliance_by_department(self, period: str = "quarter") -> ComplianceBoardOut:
        """Mandatory training on time, by department only — never by person."""
        since = today() - timedelta(days=PERIOD_DAYS.get(period, 91))
        rows = (
            await self.session.execute(
                select(Department.name, Assignment.status, Assignment.due_on, Assignment.completed_at)
                .join(User, User.id == Assignment.user_id)
                .join(Department, Department.id == User.department_id)
                .where(Assignment.is_mandatory.is_(True), Assignment.due_on.is_not(None), Assignment.due_on >= since)
            )
        ).all()
        stats: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for dept, status, due_on, completed_at in rows:
            if due_on > today() and status != AssignmentStatus.COMPLETED.value:
                continue  # not due yet: does not count either way
            stats[dept][0] += 1
            if (
                status == AssignmentStatus.COMPLETED.value
                and completed_at
                and completed_at.astimezone(org_timezone()).date() <= due_on
            ):
                stats[dept][1] += 1
        out = [
            DepartmentRateOut(department=d, assigned=a, on_time_pct=round(o / a * 100) if a else 0) for d, (a, o) in stats.items()
        ]
        return ComplianceBoardOut(rows=sorted(out, key=lambda r: -r.on_time_pct))


def _display(board: str, value: float) -> str:
    if board == "learning_hours":
        return f"{value:g} h"
    if board == "pathway_progress":
        return f"{value:g}%"
    if board == "most_improved":
        return f"+{value:g} levels"
    return f"{value:g}"
