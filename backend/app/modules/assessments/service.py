"""Skill checks (L-04), mandatory proctored tests (L-06) and their review (A-09)."""

import base64
import random
from collections.abc import Sequence
from datetime import timedelta
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError, PermissionDeniedError, ValidationFailedError
from app.core.storage import get_storage
from app.modules.assessments.models import (
    FLAG_SEVERITY,
    AttemptStatus,
    InPersonBooking,
    ProctorEvent,
    Proctoring,
    SkillTest,
    TestAttempt,
    TestInvite,
    TestQuestion,
)
from app.modules.assessments.schemas import (
    AttemptOut,
    AttemptQuestionOut,
    AttemptResultOut,
    CampaignIn,
    CampaignPreviewOut,
    FlagOut,
    MyTestOut,
    ReviewCaseOut,
    ReviewQueueItemOut,
    TestIn,
    TestOut,
)
from app.modules.audit.service import AuditService
from app.modules.identity.models import User
from app.modules.learning.bulk import BulkActionService, register_undo
from app.modules.learning.models import Assignment, AssignmentStatus, Course
from app.modules.learning.schemas import BulkResultOut
from app.modules.notifications.models import NotificationKind
from app.modules.notifications.service import NotificationService
from app.modules.settings.service import SettingsService
from app.modules.skills.models import RoleSkill, Skill, SkillLevel
from app.modules.skills.service import SkillsService
from app.shared.audience import resolve_audience
from app.shared.clock import utcnow
from app.shared.events import DomainEvent, event_bus

GRACE_SECONDS = 30
SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2}


class AssessmentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.settings = SettingsService(session)
        self.audit = AuditService(session)

    # ---- tests --------------------------------------------------------------------
    async def get_test(self, test_id: UUID) -> SkillTest:
        test = await self.session.get(SkillTest, test_id)
        if test is None or not test.is_active:
            raise NotFoundError("We could not find that test.")
        return test

    async def test_out(self, test: SkillTest) -> TestOut:
        count = await self.session.scalar(select(func.count()).where(TestQuestion.test_id == test.id))
        skill = await self.session.get(Skill, test.skill_id) if test.skill_id else None
        return TestOut.model_validate(test).model_copy(
            update={"question_count": int(count or 0), "skill_name": skill.name if skill else None}
        )

    async def list_tests(self) -> list[TestOut]:
        stmt = select(SkillTest).where(SkillTest.is_active.is_(True)).order_by(SkillTest.title)
        tests = (await self.session.scalars(stmt)).all()
        return [await self.test_out(t) for t in tests]

    async def create_test(self, data: TestIn, actor: User) -> SkillTest:
        test = SkillTest(**data.model_dump(exclude={"questions"}))
        self.session.add(test)
        await self.session.flush()
        for i, q in enumerate(data.questions, start=1):
            self.session.add(TestQuestion(test_id=test.id, position=i, **q.model_dump()))
        self.audit.record("test.created", "skill_test", test.id, actor_id=actor.id, title=test.title)
        return test

    async def my_tests(self, user: User) -> list[MyTestOut]:
        invites = (
            await self.session.scalars(
                select(TestInvite).where(TestInvite.user_id == user.id).order_by(TestInvite.due_on.is_(None), TestInvite.due_on)
            )
        ).all()
        out: list[MyTestOut] = []
        for invite in invites:
            test = await self.session.get(SkillTest, invite.test_id)
            if test is None or not test.is_active:
                continue
            attempt = await self._latest_attempt(user.id, test.id)
            status = invite.status
            if status == "pending" and attempt and attempt.status == AttemptStatus.IN_PROGRESS.value:
                status = "in_progress"
            out.append(
                MyTestOut(
                    invite_id=invite.id,
                    test=await self.test_out(test),
                    due_on=invite.due_on,
                    status=status,
                    attempt_id=attempt.id if attempt else None,
                    last_score=attempt.score if attempt else None,
                    last_level=attempt.level if attempt else None,
                )
            )
        return out

    async def _latest_attempt(self, user_id: UUID, test_id: UUID) -> TestAttempt | None:
        return (
            await self.session.scalars(
                select(TestAttempt)
                .where(TestAttempt.user_id == user_id, TestAttempt.test_id == test_id)
                .order_by(TestAttempt.started_at.desc())
                .limit(1)
            )
        ).first()

    # ---- taking a test ------------------------------------------------------------
    async def start(self, test_id: UUID, user: User, consent: bool) -> TestAttempt:
        test = await self.get_test(test_id)
        latest = await self._latest_attempt(user.id, test.id)
        if latest and latest.status == AttemptStatus.IN_PROGRESS.value and latest.deadline_at > utcnow():
            return latest  # resume after a pause
        if test.proctoring == Proctoring.CAMERA.value and not consent:
            raise ValidationFailedError("Please agree to how the test is supervised, or book an in-person test instead.")
        questions = (await self.session.scalars(select(TestQuestion.id).where(TestQuestion.test_id == test.id))).all()
        if not questions:
            raise ValidationFailedError("This test has no questions yet.")
        order = [str(q) for q in questions]
        random.shuffle(order)
        attempt = TestAttempt(
            user_id=user.id,
            test_id=test.id,
            question_order=order,
            deadline_at=utcnow() + timedelta(minutes=test.duration_minutes),
            consent_at=utcnow() if consent else None,
        )
        self.session.add(attempt)
        await self.session.flush()
        if consent:
            self.audit.record("proctoring.consent", "test_attempt", attempt.id, actor_id=user.id)
        return attempt

    async def _own_attempt(self, attempt_id: UUID, user: User) -> TestAttempt:
        attempt = await self.session.get(TestAttempt, attempt_id)
        if attempt is None or attempt.user_id != user.id:
            raise NotFoundError("We could not find that test attempt.")
        return attempt

    async def attempt_view(self, attempt_id: UUID, user: User) -> AttemptOut:
        attempt = await self._own_attempt(attempt_id, user)
        test = await self.get_test(attempt.test_id)
        by_id = {
            str(q.id): q for q in (await self.session.scalars(select(TestQuestion).where(TestQuestion.test_id == test.id))).all()
        }
        questions = [
            AttemptQuestionOut(
                id=by_id[qid].id, text=by_id[qid].text, options=by_id[qid].options, selected=attempt.answers.get(qid)
            )
            for qid in attempt.question_order
            if qid in by_id
        ]
        return AttemptOut(
            id=attempt.id,
            test_id=test.id,
            test_title=test.title,
            status=attempt.status,
            proctoring=test.proctoring,
            snapshot_seconds=await self.settings.get("proctoring.snapshot_seconds"),
            questions=questions,
            answered=len(attempt.answers),
            total=len(questions),
            seconds_left=max(0, int((attempt.deadline_at - utcnow()).total_seconds())),
        )

    async def answer(self, attempt_id: UUID, user: User, question_id: UUID, option_index: int) -> None:
        attempt = await self._own_attempt(attempt_id, user)
        self._ensure_open(attempt)
        if str(question_id) not in attempt.question_order:
            raise ValidationFailedError("That question is not part of this test.")
        attempt.answers = {**attempt.answers, str(question_id): option_index}

    @staticmethod
    def _ensure_open(attempt: TestAttempt) -> None:
        if attempt.status != AttemptStatus.IN_PROGRESS.value:
            raise ConflictError("This test is already finished.")
        if utcnow() > attempt.deadline_at + timedelta(seconds=GRACE_SECONDS):
            raise ConflictError("Time is up for this test. Your answers so far are saved; please submit.")

    async def record_proctor_event(
        self, attempt_id: UUID, user: User, kind: str, at_seconds: int, image_base64: str | None
    ) -> None:
        attempt = await self._own_attempt(attempt_id, user)
        if attempt.status != AttemptStatus.IN_PROGRESS.value:
            return
        test = await self.get_test(attempt.test_id)
        if test.proctoring != Proctoring.CAMERA.value:
            raise ValidationFailedError("This test is not supervised.")
        image_path = None
        if image_base64:
            image_path = await _store_snapshot(attempt.id, at_seconds, image_base64)
        if kind == "tab_switch":
            existing = (
                await self.session.scalars(
                    select(ProctorEvent).where(ProctorEvent.attempt_id == attempt.id, ProctorEvent.kind == "tab_switch")
                )
            ).first()
            if existing:
                existing.count += 1
                existing.at_seconds = at_seconds
                return
        severity = FLAG_SEVERITY.get(kind)
        self.session.add(
            ProctorEvent(
                attempt_id=attempt.id,
                kind=kind,
                at_seconds=at_seconds,
                severity=severity.value if severity else None,
                image_path=image_path,
            )
        )

    async def submit(self, attempt_id: UUID, user: User) -> AttemptResultOut:
        attempt = await self._own_attempt(attempt_id, user)
        if attempt.status != AttemptStatus.IN_PROGRESS.value:
            return await self.result(attempt_id, user)
        test = await self.get_test(attempt.test_id)
        questions = (await self.session.scalars(select(TestQuestion).where(TestQuestion.test_id == test.id))).all()
        correct = sum(1 for q in questions if attempt.answers.get(str(q.id)) == q.answer_index)
        attempt.score = round(correct / len(questions) * 100) if questions else 0
        attempt.submitted_at = utcnow()
        if test.skill_id:
            attempt.level = await SkillsService(self.session).level_for_score(attempt.score)
        if test.pass_mark is not None:
            attempt.passed = attempt.score >= test.pass_mark
        flags = await self._flag_count(attempt.id)
        if test.proctoring == Proctoring.CAMERA.value and flags:
            # Nothing is failed automatically: a trained reviewer decides.
            attempt.status = AttemptStatus.UNDER_REVIEW.value
        else:
            await self._finalize(attempt, test)
        await self.session.flush()
        return await self.result(attempt.id, user)

    async def _flag_count(self, attempt_id: UUID) -> int:
        return int(
            await self.session.scalar(
                select(func.count()).where(ProctorEvent.attempt_id == attempt_id, ProctorEvent.severity.is_not(None))
            )
            or 0
        )

    async def _finalize(self, attempt: TestAttempt, test: SkillTest) -> None:
        """The attempt counts: store the level, close the invite, issue certificates."""
        attempt.status = AttemptStatus.VALID.value
        attempt.case_closed_at = utcnow()
        if test.skill_id and attempt.level is not None:
            await SkillsService(self.session).record_level(
                attempt.user_id, test.skill_id, level=attempt.level, score=attempt.score, source="test"
            )
        invites = (
            await self.session.scalars(
                select(TestInvite).where(TestInvite.user_id == attempt.user_id, TestInvite.test_id == test.id)
            )
        ).all()
        for invite in invites:
            invite.status = "done"
        await event_bus.publish(
            self.session,
            DomainEvent("test.completed", {"user_id": attempt.user_id, "test_id": test.id, "score": attempt.score}),
        )
        if test.pass_mark is not None and attempt.passed:
            await self._complete_linked_courses(attempt, test)
            await event_bus.publish(
                self.session,
                DomainEvent(
                    "certification.passed",
                    {"user_id": attempt.user_id, "test_id": test.id, "score": attempt.score, "attempt_id": attempt.id},
                ),
            )

    async def _complete_linked_courses(self, attempt: TestAttempt, test: SkillTest) -> None:
        from app.modules.learning.player_service import PlayerService

        rows = (
            await self.session.execute(
                select(Assignment, Course)
                .join(Course, Course.id == Assignment.course_id)
                .where(
                    Course.final_test_id == test.id,
                    Assignment.user_id == attempt.user_id,
                    Assignment.status != AssignmentStatus.COMPLETED.value,
                )
            )
        ).all()
        for assignment, course in rows:
            # Course completion without re-issuing: the test itself issues the certificate.
            course_kind = course.kind
            course.kind = "self_paced"
            await PlayerService(self.session).mark_completed(assignment, course, score=attempt.score)
            course.kind = course_kind

    async def result(self, attempt_id: UUID, user: User) -> AttemptResultOut:
        attempt = await self._own_attempt(attempt_id, user)
        test = await self.get_test(attempt.test_id)
        level_names = await self.settings.get("skills.level_names")
        rank = None
        if test.skill_id and attempt.status == AttemptStatus.VALID.value:
            rank = await SkillsService(self.session)._rank_of(user.id, test.skill_id)
        required = None
        if test.skill_id and user.job_role_id:
            required = await self.session.scalar(
                select(RoleSkill.required_level).where(
                    RoleSkill.job_role_id == user.job_role_id, RoleSkill.skill_id == test.skill_id
                )
            )
        left = await self.skills_left_to_check(user)
        certificate_id = None
        if attempt.passed and attempt.status == AttemptStatus.VALID.value:
            from app.modules.certificates.models import Certificate

            certificate_id = await self.session.scalar(
                select(Certificate.id)
                .where(Certificate.user_id == user.id, Certificate.test_id == test.id)
                .order_by(Certificate.issued_at.desc())
                .limit(1)
            )
        return AttemptResultOut(
            attempt_id=attempt.id,
            status=attempt.status,
            score=attempt.score or 0,
            level=attempt.level,
            level_name=level_names[attempt.level] if attempt.level is not None else None,
            passed=attempt.passed,
            pass_mark=test.pass_mark,
            rank=rank.rank if rank else None,
            out_of=rank.out_of if rank else None,
            top_percent=rank.top_percent if rank else None,
            required_level=required,
            meets_requirement=(attempt.level or 0) >= required if required is not None and attempt.level is not None else None,
            skills_left_to_check=left,
            message=_result_message(attempt, test, left),
            certificate_id=certificate_id,
        )

    async def skills_left_to_check(self, user: User) -> int:
        if not user.job_role_id:
            return 0
        required = select(RoleSkill.skill_id).where(RoleSkill.job_role_id == user.job_role_id)
        tested = select(SkillLevel.skill_id).where(SkillLevel.user_id == user.id)
        testable = select(SkillTest.skill_id).where(SkillTest.is_active.is_(True), SkillTest.skill_id.is_not(None))
        stmt = select(func.count()).where(
            RoleSkill.job_role_id == user.job_role_id,
            RoleSkill.skill_id.in_(required),
            RoleSkill.skill_id.not_in(tested),
            RoleSkill.skill_id.in_(testable),
        )
        return int(await self.session.scalar(stmt) or 0)

    # ---- in-person alternative ---------------------------------------------------------
    async def book_in_person(self, test_id: UUID, user: User, preferred_dates: str) -> InPersonBooking:
        await self.get_test(test_id)
        booking = InPersonBooking(user_id=user.id, test_id=test_id, preferred_dates=preferred_dates)
        self.session.add(booking)
        await self.session.flush()
        self.audit.record("test.in_person_requested", "skill_test", test_id, actor_id=user.id)
        return booking

    async def bookings(self) -> Sequence[InPersonBooking]:
        return (await self.session.scalars(select(InPersonBooking).order_by(InPersonBooking.created_at.desc()))).all()

    # ---- campaigns (A-03 "Send skill tests") ------------------------------------------
    async def _campaign_targets(self, data: CampaignIn) -> tuple[str, list[tuple[UUID, UUID]], int]:
        audience = await resolve_audience(self.session, data.audience)
        for test_id in data.test_ids:
            await self.get_test(test_id)
        existing = set(
            (
                await self.session.execute(
                    select(TestInvite.user_id, TestInvite.test_id).where(
                        TestInvite.status == "pending", TestInvite.test_id.in_(data.test_ids)
                    )
                )
            ).all()
        )
        pairs = [(u, t) for u in audience.user_ids for t in data.test_ids if (u, t) not in existing]
        return audience.label, pairs, len(audience.user_ids)

    async def campaign_preview(self, data: CampaignIn) -> CampaignPreviewOut:
        label, pairs, people = await self._campaign_targets(data)
        return CampaignPreviewOut(audience_label=label, people=people, tests=len(data.test_ids), new_invites=len(pairs))

    async def send_campaign(self, data: CampaignIn, actor: User | None, *, automatic: bool = False) -> BulkResultOut:
        label, pairs, _ = await self._campaign_targets(data)
        bulk = await BulkActionService(self.session).start("send_tests", actor, f"Skill tests to {label}", len(pairs))
        notified: set[UUID] = set()
        notifications = NotificationService(self.session)
        for user_id, test_id in pairs:
            self.session.add(
                TestInvite(
                    user_id=user_id,
                    test_id=test_id,
                    due_on=data.due_on,
                    assigned_by_id=actor.id if actor else None,
                    batch_id=bulk.id,
                )
            )
            if user_id not in notified:
                notified.add(user_id)
                await notifications.notify(
                    user_id,
                    kind=NotificationKind.SYSTEM,
                    title="A short skill check is ready for you",
                    body="No pass or fail: it shows your level and helps plan your learning.",
                    link="/learn/tests",
                    actions=[{"label": "Start", "href": "/learn/tests"}],
                    automatic=automatic,
                )
        await self.session.flush()
        return BulkResultOut(bulk_action_id=bulk.id, count=len(pairs), undo_until=bulk.undo_until, summary=bulk.summary)

    # ---- proctoring review (A-09) --------------------------------------------------------
    async def review_queue(self) -> list[ReviewQueueItemOut]:
        attempts = (
            await self.session.scalars(
                select(TestAttempt)
                .where(TestAttempt.status == AttemptStatus.UNDER_REVIEW.value)
                .order_by(TestAttempt.submitted_at)
            )
        ).all()
        items: list[ReviewQueueItemOut] = []
        for attempt in attempts:
            flags = (
                await self.session.scalars(
                    select(ProctorEvent).where(ProctorEvent.attempt_id == attempt.id, ProctorEvent.severity.is_not(None))
                )
            ).all()
            test = await self.session.get(SkillTest, attempt.test_id)
            person = await self.session.get(User, attempt.user_id)
            severity = max((f.severity or "low" for f in flags), key=lambda s: SEVERITY_ORDER[s], default="low")
            items.append(
                ReviewQueueItemOut(
                    attempt_id=attempt.id,
                    test_title=test.title if test else "Test",
                    employee_code=person.employee_code if person else None,
                    flags=len(flags),
                    severity=severity,
                    submitted_at=attempt.submitted_at,
                    is_appeal=attempt.appeal_status == "open",
                )
            )
        return sorted(items, key=lambda i: -SEVERITY_ORDER[i.severity])

    async def review_case(self, attempt_id: UUID, reviewer: User) -> ReviewCaseOut:
        attempt = await self.session.get(TestAttempt, attempt_id)
        if attempt is None:
            raise NotFoundError("We could not find that attempt.")
        test = await self.session.get(SkillTest, attempt.test_id)
        person = await self.session.get(User, attempt.user_id)
        flags = (
            await self.session.scalars(
                select(ProctorEvent)
                .where(ProctorEvent.attempt_id == attempt.id, ProctorEvent.severity.is_not(None))
                .order_by(ProctorEvent.at_seconds)
            )
        ).all()
        questions = int(await self.session.scalar(select(func.count()).where(TestQuestion.test_id == attempt.test_id)) or 0)
        end = attempt.submitted_at or utcnow()
        seconds = int((end - attempt.started_at).total_seconds())
        # Every view of proctoring evidence is logged.
        self.audit.record("proctoring.evidence_viewed", "test_attempt", attempt.id, actor_id=reviewer.id)
        return ReviewCaseOut(
            attempt_id=attempt.id,
            test_title=test.title if test else "Test",
            employee_code=person.employee_code if person else None,
            question_count=questions,
            score=attempt.score,
            minutes=round(seconds / 60),
            duration_seconds=seconds,
            flags=[
                FlagOut(
                    id=f.id,
                    kind=f.kind,
                    at_seconds=f.at_seconds,
                    severity=f.severity,
                    count=f.count,
                    has_image=bool(f.image_path),
                )
                for f in flags
            ],
            status=attempt.status,
            appeal_note=attempt.appeal_note,
            previous_decision=attempt.review_note and (attempt.appeal_status and "see note"),
            previous_note=attempt.review_note if attempt.appeal_status else None,
        )

    async def snapshot(self, event_id: UUID, reviewer: User) -> bytes:
        event = await self.session.get(ProctorEvent, event_id)
        if event is None or not event.image_path:
            raise NotFoundError("There is no picture for this flag.")
        self.audit.record("proctoring.snapshot_viewed", "proctor_event", event.id, actor_id=reviewer.id)
        return await get_storage().read(event.image_path)

    async def decide(self, attempt_id: UUID, decision: str, note: str, reviewer: User) -> TestAttempt:
        attempt = await self.session.get(TestAttempt, attempt_id)
        if attempt is None:
            raise NotFoundError("We could not find that attempt.")
        if attempt.status != AttemptStatus.UNDER_REVIEW.value:
            raise ConflictError("This attempt is not waiting for review.")
        if attempt.user_id == reviewer.id:
            raise PermissionDeniedError("You cannot review your own test.")
        is_appeal = attempt.appeal_status == "open"
        if is_appeal and reviewer.id == attempt.reviewer_id:
            raise PermissionDeniedError("A different reviewer must decide the appeal.")
        test = await self.get_test(attempt.test_id)
        previous_status = attempt.reviewer_id and attempt.status
        if is_appeal:
            attempt.appeal_reviewer_id = reviewer.id
            attempt.appeal_status = "overturned" if decision == "valid" else "upheld"
        else:
            attempt.reviewer_id = reviewer.id
        attempt.review_note = note
        attempt.reviewed_at = utcnow()
        notifications = NotificationService(self.session)
        if decision == "valid":
            await self._finalize(attempt, test)
            title, body = f'Your "{test.title}" result is confirmed', "The reviewer confirmed your attempt."
        elif decision == "retest":
            attempt.status = AttemptStatus.RETEST.value
            attempt.case_closed_at = utcnow()
            for invite in (
                await self.session.scalars(
                    select(TestInvite).where(TestInvite.user_id == attempt.user_id, TestInvite.test_id == test.id)
                )
            ).all():
                invite.status = "pending"
            title, body = f'Please take "{test.title}" again', note
        else:
            attempt.status = AttemptStatus.INVALID.value
            attempt.case_closed_at = utcnow()
            title, body = f'Your "{test.title}" attempt could not be accepted', f"{note} You can appeal this decision."
        await notifications.notify(
            attempt.user_id,
            kind=NotificationKind.SYSTEM,
            title=title,
            body=body,
            link=f"/learn/tests/attempts/{attempt.id}",
            related=("test_attempt", attempt.id),
        )
        self.audit.record(
            "proctoring.decision",
            "test_attempt",
            attempt.id,
            actor_id=reviewer.id,
            decision=decision,
            note=note,
            appeal=is_appeal,
            previous=previous_status,
        )
        return attempt

    async def appeal(self, attempt_id: UUID, user: User, note: str) -> TestAttempt:
        attempt = await self._own_attempt(attempt_id, user)
        if attempt.status not in {AttemptStatus.INVALID.value, AttemptStatus.RETEST.value}:
            raise ConflictError("Only an invalid or retest decision can be appealed.")
        if attempt.appeal_status is not None:
            raise ConflictError("This attempt was already appealed.")
        attempt.appeal_note = note
        attempt.appeal_status = "open"
        attempt.status = AttemptStatus.UNDER_REVIEW.value
        attempt.case_closed_at = None
        self.audit.record("proctoring.appeal", "test_attempt", attempt.id, actor_id=user.id)
        return attempt

    async def purge_old_snapshots(self) -> int:
        """Pictures are deleted N days after the case closes (retention setting)."""
        days = await self.settings.get("proctoring.retention_days")
        cutoff = utcnow() - timedelta(days=days)
        closed = select(TestAttempt.id).where(TestAttempt.case_closed_at.is_not(None), TestAttempt.case_closed_at < cutoff)
        events = (
            await self.session.scalars(
                select(ProctorEvent).where(ProctorEvent.attempt_id.in_(closed), ProctorEvent.image_path.is_not(None))
            )
        ).all()
        for event in events:
            if event.image_path:
                await get_storage().delete(event.image_path)
            event.image_path = None
        await self.session.execute(
            delete(ProctorEvent).where(ProctorEvent.attempt_id.in_(closed), ProctorEvent.kind == "snapshot")
        )
        return len(events)


async def _store_snapshot(attempt_id: UUID, at_seconds: int, image_base64: str) -> str:
    try:
        data = base64.b64decode(image_base64.split(",")[-1], validate=True)
    except ValueError as exc:
        raise ValidationFailedError("The picture could not be read.") from exc
    return await get_storage().save(f"proctoring/{attempt_id}/{at_seconds:06d}.jpg", data, "image/jpeg")


def _result_message(attempt: TestAttempt, test: SkillTest, left: int) -> str:
    if attempt.status == AttemptStatus.UNDER_REVIEW.value:
        return "Thank you. A trained reviewer is checking your attempt. Nothing is failed automatically."
    if test.pass_mark is not None:
        if attempt.passed:
            return "You passed. Your certificate is ready."
        return f"You scored {attempt.score}%. The pass mark is {test.pass_mark}%. You can try again."
    if left:
        return f"{left} more skill{'s' if left != 1 else ''} to check. Your pathway is ready after the last one."
    return "All your skills are checked. Your pathway is ready."


async def _undo_test_invites(session: AsyncSession, batch_id: UUID) -> int:
    result = await session.execute(delete(TestInvite).where(TestInvite.batch_id == batch_id, TestInvite.status == "pending"))
    return int(result.rowcount or 0)  # type: ignore[attr-defined]


register_undo("send_tests", _undo_test_invites)
