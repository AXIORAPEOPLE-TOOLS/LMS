"""My pathway (L-02): build from gaps, approve, and move through the four steps."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError, PermissionDeniedError, ValidationFailedError
from app.modules.assessments.models import SkillTest, TestInvite
from app.modules.audit.service import AuditService
from app.modules.identity.models import User
from app.modules.learning.models import Assignment, Course, CourseStatus
from app.modules.notifications.models import NotificationKind
from app.modules.notifications.service import NotificationService
from app.modules.pathways import rules
from app.modules.pathways.models import STEP_ORDER, Pathway, PathwayItem, PathwayStatus, Step
from app.modules.pathways.schemas import NextStepOut, PathwayItemOut, PathwayOut, WaveOut
from app.modules.settings.service import SettingsService
from app.modules.skills.models import JobRole, RoleSkill, Skill, SkillLevel
from app.shared.clock import utcnow
from app.shared.events import DomainEvent, event_bus

PRACTISE_TASK = "Use it on a real task this week and write what you did. Your manager signs it off."


class PathwayService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.settings = SettingsService(session)
        self.audit = AuditService(session)

    # ---- reads ---------------------------------------------------------------------
    async def current(self, user_id: UUID) -> Pathway | None:
        return (
            await self.session.scalars(
                select(Pathway).where(Pathway.user_id == user_id).order_by(Pathway.created_at.desc()).limit(1)
            )
        ).first()

    async def items(self, pathway_id: UUID) -> Sequence[PathwayItem]:
        return (
            await self.session.scalars(
                select(PathwayItem).where(PathwayItem.pathway_id == pathway_id).order_by(PathwayItem.wave, PathwayItem.position)
            )
        ).all()

    async def view(self, user_id: UUID) -> PathwayOut | None:
        pathway = await self.current(user_id)
        if pathway is None:
            return None
        items = await self.items(pathway.id)
        names = await self._names(items)
        hours_per_week = pathway.hours_per_week or 3
        active_wave = self._active_wave(pathway, items)
        waves: list[WaveOut] = []
        for number in sorted({i.wave for i in items}):
            wave_items = [i for i in items if i.wave == number]
            done = sum(STEP_ORDER.index(Step(i.step)) for i in wave_items)
            total = len(wave_items) * (len(STEP_ORDER) - 1)
            hours = sum(i.estimated_hours for i in wave_items)
            status = "done" if all(i.step == Step.DONE for i in wave_items) else ("active" if number == active_wave else "locked")
            waves.append(
                WaveOut(
                    number=number,
                    status=status,
                    hours=round(hours, 1),
                    weeks=rules.wave_weeks(hours, hours_per_week),
                    progress_pct=round(done / total * 100) if total else 100,
                    items=[self._item_out(i, names) for i in wave_items],
                )
            )
        all_steps = len(items) * (len(STEP_ORDER) - 1)
        all_done = sum(STEP_ORDER.index(Step(i.step)) for i in items)
        target = await self.session.get(JobRole, pathway.target_role_id) if pathway.target_role_id else None
        approver = await self.session.get(User, pathway.approved_by_id) if pathway.approved_by_id else None
        return PathwayOut(
            id=pathway.id,
            user_id=pathway.user_id,
            status=pathway.status,
            hours_per_week=hours_per_week,
            target_role_id=pathway.target_role_id,
            target_role_name=target.name if target else None,
            approved_by_name=approver.full_name if approver else None,
            current_wave=active_wave,
            total_waves=len(waves),
            progress_pct=round(all_done / all_steps * 100) if all_steps else 0,
            waves=waves,
            next_step=self._next_step(pathway, items, active_wave, names),
        )

    @staticmethod
    def _active_wave(pathway: Pathway, items: Sequence[PathwayItem]) -> int | None:
        if pathway.status != PathwayStatus.ACTIVE.value:
            return None
        open_waves = sorted({i.wave for i in items if i.step != Step.DONE})
        return open_waves[0] if open_waves else None

    async def _names(self, items: Sequence[PathwayItem]) -> dict[UUID, str]:
        ids = (
            {i.skill_id for i in items}
            | {i.course_id for i in items if i.course_id}
            | {i.mentor_id for i in items if i.mentor_id}
        )
        names: dict[UUID, str] = {}
        if not ids:
            return names
        names |= dict((await self.session.execute(select(Skill.id, Skill.name).where(Skill.id.in_(ids)))).all())
        names |= dict((await self.session.execute(select(Course.id, Course.title).where(Course.id.in_(ids)))).all())
        names |= dict((await self.session.execute(select(User.id, User.full_name).where(User.id.in_(ids)))).all())
        return names

    @staticmethod
    def _item_out(item: PathwayItem, names: dict[UUID, str]) -> PathwayItemOut:
        return PathwayItemOut(
            id=item.id,
            wave=item.wave,
            position=item.position,
            skill_id=item.skill_id,
            skill_name=names.get(item.skill_id, "Skill"),
            from_level=item.from_level,
            to_level=item.to_level,
            step=item.step,
            course_id=item.course_id,
            course_title=names.get(item.course_id) if item.course_id else None,
            mentor_id=item.mentor_id,
            mentor_name=names.get(item.mentor_id) if item.mentor_id else None,
            practise_task=item.practise_task,
            practise_evidence=item.practise_evidence,
            practise_submitted_at=item.practise_submitted_at,
            waiting_for_signoff=item.step == Step.PRACTISE and item.practise_submitted_at is not None,
            certificate_on_pass=item.certificate_on_pass,
            estimated_hours=item.estimated_hours,
        )

    def _next_step(
        self, pathway: Pathway, items: Sequence[PathwayItem], wave: int | None, names: dict[UUID, str]
    ) -> NextStepOut | None:
        if wave is None:
            return None
        candidates = [i for i in items if i.wave == wave and i.step != Step.DONE]
        # Prefer something the learner can do now (not waiting for the manager).
        candidates.sort(key=lambda i: (i.step == Step.PRACTISE and i.practise_submitted_at is not None, i.position))
        item = candidates[0]
        skill = names.get(item.skill_id, "this skill")
        if item.step == Step.LEARN:
            course = names.get(item.course_id) if item.course_id else None
            return NextStepOut(
                item_id=item.id,
                step=item.step,
                title=f"Take the course: {course or skill}",
                description=f"Takes you from level {item.from_level} to {item.to_level} in {skill}.",
                action_label="Continue course",
                href=f"/learn/courses/{item.course_id}" if item.course_id else f"/learn/catalogue?skill={item.skill_id}",
            )
        if item.step == Step.PRACTISE:
            waiting = item.practise_submitted_at is not None
            return NextStepOut(
                item_id=item.id,
                step=item.step,
                title=f"Use {skill} at work",
                description="Waiting for your manager to sign it off." if waiting else item.practise_task,
                action_label="Waiting for sign-off" if waiting else "Tell us what you did",
                href=None,
            )
        if item.step == Step.CONNECT:
            mentor = names.get(item.mentor_id) if item.mentor_id else None
            return NextStepOut(
                item_id=item.id,
                step=item.step,
                title=f"Talk to {mentor or 'an expert at work'} for 30 minutes",
                description=f"Ask how they use {skill} in their work.",
                action_label="Done, we talked",
                href=None,
            )
        return NextStepOut(
            item_id=item.id,
            step=item.step,
            title=f"Take the {skill} test",
            description=f"Reach level {item.to_level} to finish this skill.",
            action_label="Start test",
            href="/learn/tests",
        )

    # ---- build ---------------------------------------------------------------------
    async def generate(self, user: User, actor: User, *, target_role_id: UUID | None = None) -> Pathway:
        if not user.job_role_id and not target_role_id:
            raise ValidationFailedError("A role is needed to build a pathway.")
        required: dict[UUID, int] = {}
        for role_id in filter(None, [user.job_role_id, target_role_id]):
            for link in (await self.session.scalars(select(RoleSkill).where(RoleSkill.job_role_id == role_id))).all():
                required[link.skill_id] = max(required.get(link.skill_id, 0), link.required_level)
        levels = {
            sl.skill_id: sl.level
            for sl in (await self.session.scalars(select(SkillLevel).where(SkillLevel.user_id == user.id))).all()
        }
        skills = {s.id: s for s in (await self.session.scalars(select(Skill).where(Skill.id.in_(required)))).all()}

        pathway = await self.current(user.id)
        if pathway is None or pathway.status == PathwayStatus.COMPLETED.value:
            pathway = Pathway(user_id=user.id, hours_per_week=user.hours_per_week or 3)
            self.session.add(pathway)
            await self.session.flush()
        kept = [i for i in await self.items(pathway.id) if i.step == Step.DONE]
        await self.session.execute(
            delete(PathwayItem).where(PathwayItem.pathway_id == pathway.id, PathwayItem.step != Step.DONE.value)
        )
        done_skills = {i.skill_id for i in kept}
        gaps = [
            rules.GapInput(sid, skills[sid].name, req, levels.get(sid), skills[sid].is_mandatory)
            for sid, req in required.items()
            if sid in skills and sid not in done_skills
        ]
        planned = rules.plan_waves(
            gaps,
            wave_size=await self.settings.get("pathways.wave_size"),
            hours_per_level=await self.settings.get("pathways.hours_per_level"),
        )
        wave_offset = max((i.wave for i in kept), default=0)
        for plan in planned:
            course = await self._course_for(plan.skill_id)
            self.session.add(
                PathwayItem(
                    pathway_id=pathway.id,
                    wave=plan.wave + wave_offset,
                    position=plan.position,
                    skill_id=plan.skill_id,
                    from_level=plan.from_level,
                    to_level=plan.to_level,
                    course_id=course.id if course else None,
                    mentor_id=await self._mentor_for(plan.skill_id, user.id, plan.to_level),
                    practise_task=PRACTISE_TASK,
                    certificate_on_pass=bool(course and course.kind == "certification"),
                    estimated_hours=plan.estimated_hours,
                )
            )
        pathway.target_role_id = target_role_id or pathway.target_role_id
        needs_approval = await self.settings.get("pathways.require_manager_approval")
        pathway.status = (
            PathwayStatus.PENDING_APPROVAL.value if needs_approval and user.manager_id else PathwayStatus.ACTIVE.value
        )
        await self.session.flush()
        if pathway.status == PathwayStatus.PENDING_APPROVAL.value and user.manager_id:
            await NotificationService(self.session).notify(
                user.manager_id,
                kind=NotificationKind.APPROVAL,
                title=f"Pathway for {user.full_name} needs your approval",
                link="/team/approvals",
                related=("pathway", pathway.id),
            )
        elif pathway.status == PathwayStatus.ACTIVE.value:
            await self._open_first_wave(pathway)
        self.audit.record("pathway.generated", "pathway", pathway.id, actor_id=actor.id, items=len(planned))
        return pathway

    async def _course_for(self, skill_id: UUID) -> Course | None:
        return (
            await self.session.scalars(
                select(Course)
                .where(Course.skill_id == skill_id, Course.status == CourseStatus.PUBLISHED.value)
                .order_by(Course.from_level)
                .limit(1)
            )
        ).first()

    async def _mentor_for(self, skill_id: UUID, user_id: UUID, to_level: int) -> UUID | None:
        """The strongest tested colleague in this skill becomes the 'connect' expert."""
        return (
            await self.session.scalars(
                select(SkillLevel.user_id)
                .join(User, User.id == SkillLevel.user_id)
                .where(
                    SkillLevel.skill_id == skill_id,
                    SkillLevel.user_id != user_id,
                    SkillLevel.level >= max(4, to_level),
                    User.is_active.is_(True),
                )
                .order_by(SkillLevel.level.desc(), SkillLevel.score.desc().nulls_last())
                .limit(1)
            )
        ).first()

    async def approve(self, pathway_id: UUID, manager: User) -> Pathway:
        pathway = await self.session.get(Pathway, pathway_id)
        if pathway is None:
            raise NotFoundError("We could not find that pathway.")
        owner = await self.session.get(User, pathway.user_id)
        if not manager.has_role("admin") and (owner is None or owner.manager_id != manager.id):
            raise PermissionDeniedError("Only the person's manager can approve this pathway.")
        if pathway.status != PathwayStatus.PENDING_APPROVAL.value:
            raise ConflictError("This pathway is not waiting for approval.")
        pathway.status = PathwayStatus.ACTIVE.value
        pathway.approved_by_id = manager.id
        pathway.approved_at = utcnow()
        await self._open_first_wave(pathway)
        await NotificationService(self.session).notify(
            pathway.user_id,
            kind=NotificationKind.SYSTEM,
            title="Your pathway is ready",
            body="Your manager approved it. Your first step is waiting.",
            link="/learn/path",
            related=("pathway", pathway.id),
        )
        self.audit.record("pathway.approved", "pathway", pathway.id, actor_id=manager.id)
        return pathway

    async def _open_first_wave(self, pathway: Pathway) -> None:
        """Courses in the active wave become assignments so they show on the home screen."""
        items = await self.items(pathway.id)
        wave = self._active_wave(pathway, items)
        if wave is None:
            return
        for item in items:
            if item.wave != wave or not item.course_id or item.step != Step.LEARN:
                continue
            exists = (
                await self.session.scalars(
                    select(Assignment.id).where(Assignment.user_id == pathway.user_id, Assignment.course_id == item.course_id)
                )
            ).first()
            if not exists:
                self.session.add(Assignment(user_id=pathway.user_id, course_id=item.course_id, source="pathway"))
        await self.session.flush()

    # ---- moving through steps --------------------------------------------------------
    async def _own_item(self, item_id: UUID, user: User) -> tuple[PathwayItem, Pathway]:
        item = await self.session.get(PathwayItem, item_id)
        pathway = await self.session.get(Pathway, item.pathway_id) if item else None
        if item is None or pathway is None or pathway.user_id != user.id:
            raise NotFoundError("We could not find that step.")
        if pathway.status != PathwayStatus.ACTIVE.value:
            raise ConflictError("Your pathway is waiting for your manager's approval.")
        if self._active_wave(pathway, await self.items(pathway.id)) != item.wave:
            raise ConflictError("This wave opens when the current one is done.")
        return item, pathway

    async def mark_learned(self, item_id: UUID, user: User) -> None:
        item, pathway = await self._own_item(item_id, user)
        if item.step != Step.LEARN:
            raise ConflictError("This step is already done.")
        if item.course_id:
            raise ConflictError("Finish the course to complete this step.")
        await self._advance(item, pathway)

    async def submit_evidence(self, item_id: UUID, user: User, evidence: str) -> None:
        item, _ = await self._own_item(item_id, user)
        if item.step != Step.PRACTISE:
            raise ConflictError("This is not the practise step.")
        item.practise_evidence = evidence
        item.practise_submitted_at = utcnow()
        if user.manager_id:
            await NotificationService(self.session).notify(
                user.manager_id,
                kind=NotificationKind.APPROVAL,
                title=f"{user.full_name} asks you to sign off a practise task",
                body=evidence[:200],
                link="/team/approvals",
                related=("pathway_item", item.id),
            )
        else:
            pathway = await self.session.get(Pathway, item.pathway_id)
            assert pathway is not None
            await self._advance(item, pathway)  # nobody to sign off: move on

    async def sign_off(self, item_id: UUID, manager: User, approve: bool) -> None:
        item = await self.session.get(PathwayItem, item_id)
        pathway = await self.session.get(Pathway, item.pathway_id) if item else None
        if item is None or pathway is None:
            raise NotFoundError("We could not find that step.")
        owner = await self.session.get(User, pathway.user_id)
        if not manager.has_role("admin") and (owner is None or owner.manager_id != manager.id):
            raise PermissionDeniedError("Only the person's manager can sign this off.")
        if item.step != Step.PRACTISE or item.practise_submitted_at is None:
            raise ConflictError("Nothing is waiting for sign-off here.")
        if approve:
            item.practise_signed_off_by = manager.id
            await self._advance(item, pathway)
        else:
            item.practise_submitted_at = None  # back to the learner
        await NotificationService(self.session).notify(
            pathway.user_id,
            kind=NotificationKind.SYSTEM,
            title="Your practise task was signed off" if approve else "Your manager asked for a bit more practice",
            link="/learn/path",
            related=("pathway_item", item.id),
        )
        self.audit.record("pathway.practise_signoff", "pathway_item", item.id, actor_id=manager.id, approved=approve)

    async def mark_connected(self, item_id: UUID, user: User) -> None:
        item, pathway = await self._own_item(item_id, user)
        if item.step != Step.CONNECT:
            raise ConflictError("This is not the connect step.")
        await self._advance(item, pathway)

    async def _advance(self, item: PathwayItem, pathway: Pathway) -> None:
        index = STEP_ORDER.index(Step(item.step))
        item.step = STEP_ORDER[min(index + 1, len(STEP_ORDER) - 1)].value
        if item.step == Step.PROVE:
            await self._invite_to_retest(pathway.user_id, item.skill_id)
        await self.session.flush()
        await self._check_completion(pathway)

    async def _invite_to_retest(self, user_id: UUID, skill_id: UUID) -> None:
        test = (
            await self.session.scalars(
                select(SkillTest).where(SkillTest.skill_id == skill_id, SkillTest.is_active.is_(True)).limit(1)
            )
        ).first()
        if test is None:
            return
        pending = (
            await self.session.scalars(
                select(TestInvite.id).where(
                    TestInvite.user_id == user_id, TestInvite.test_id == test.id, TestInvite.status == "pending"
                )
            )
        ).first()
        if not pending:
            self.session.add(TestInvite(user_id=user_id, test_id=test.id))

    async def _check_completion(self, pathway: Pathway) -> None:
        items = await self.items(pathway.id)
        if items and all(i.step == Step.DONE for i in items):
            pathway.status = PathwayStatus.COMPLETED.value
            pathway.completed_at = utcnow()
            await event_bus.publish(self.session, DomainEvent("pathway.completed", {"user_id": pathway.user_id}))
        else:
            await self._open_first_wave(pathway)

    # ---- reactions to other modules (called by subscribers) -----------------------------
    async def on_course_completed(self, user_id: UUID, course_id: UUID) -> None:
        pathway = await self.current(user_id)
        if pathway is None or pathway.status != PathwayStatus.ACTIVE.value:
            return
        for item in await self.items(pathway.id):
            if item.course_id == course_id and item.step == Step.LEARN:
                await self._advance(item, pathway)

    async def on_level_recorded(self, user_id: UUID, skill_id: UUID, level: int) -> None:
        pathway = await self.current(user_id)
        if pathway is None or pathway.status == PathwayStatus.COMPLETED.value:
            return
        for item in await self.items(pathway.id):
            if item.skill_id == skill_id and item.step == Step.PROVE and level >= item.to_level:
                item.step = Step.DONE.value
                await self.session.flush()
                await self._check_completion(pathway)

    async def pending_approvals(self, manager: User) -> Sequence[Pathway]:
        team = select(User.id).where(User.manager_id == manager.id)
        return (
            await self.session.scalars(
                select(Pathway).where(Pathway.status == PathwayStatus.PENDING_APPROVAL.value, Pathway.user_id.in_(team))
            )
        ).all()

    async def pending_signoffs(self, manager: User) -> Sequence[tuple[PathwayItem, Pathway]]:
        team = select(User.id).where(User.manager_id == manager.id)
        rows = (
            await self.session.execute(
                select(PathwayItem, Pathway)
                .join(Pathway, Pathway.id == PathwayItem.pathway_id)
                .where(
                    Pathway.user_id.in_(team),
                    PathwayItem.step == Step.PRACTISE.value,
                    PathwayItem.practise_submitted_at.is_not(None),
                )
            )
        ).all()
        return [(r[0], r[1]) for r in rows]
