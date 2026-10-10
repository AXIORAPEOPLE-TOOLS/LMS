"""Runs the helpers. Course and quiz runs happen in the worker (`agents.run`); the assignment helper
reads the request at once, then waits for HR to confirm the preview (golden rule 4)."""

import logging
from datetime import date, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ConflictError, NotFoundError, ValidationFailedError
from app.core.queue import Queues, defer_job
from app.modules.agents import quiz_writer
from app.modules.agents.checks import check_course, check_questions, trial_run
from app.modules.agents.material import find_material
from app.modules.agents.models import AgentRun, RunKind, RunStatus
from app.modules.agents.schemas import (
    AssignConfirmIn,
    AssignPlanOut,
    AssignRequestIn,
    CourseBriefIn,
    QuizBriefIn,
    RunOut,
    RunStepOut,
    RunSummaryOut,
)
from app.modules.agents.steps import StepLog, initial_steps
from app.modules.ai.provider import CourseBrief, Passage
from app.modules.ai.service import get_assistant
from app.modules.audit.service import AuditService
from app.modules.identity.models import Department, User
from app.modules.learning.assignment_service import AssignmentService
from app.modules.learning.course_service import CourseService
from app.modules.learning.models import Assignment, Course, CourseKind, CourseStatus, Lesson, LessonKind
from app.modules.learning.schemas import AssignIn
from app.modules.notifications.models import NotificationKind
from app.modules.notifications.service import NotificationService
from app.modules.settings.service import SettingsService
from app.modules.skills.models import JobRole
from app.shared.audience import Audience
from app.shared.clock import today, utcnow

logger = logging.getLogger(__name__)


class AgentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.audit = AuditService(session)

    # ---- reads ------------------------------------------------------------------------------
    async def get_run(self, run_id: UUID) -> AgentRun:
        run = await self.session.get(AgentRun, run_id)
        if run is None:
            raise NotFoundError("We could not find that run.")
        return run

    async def list_runs(self, *, limit: int = 30) -> list[RunSummaryOut]:
        runs = (await self.session.scalars(select(AgentRun).order_by(AgentRun.created_at.desc()).limit(limit))).all()
        for run in runs:
            await self._sync(run)
        return [_summary(r) for r in runs]

    async def detail(self, run_id: UUID) -> RunOut:
        run = await self.get_run(run_id)
        course = await self._sync(run)
        plan = None
        if run.kind == RunKind.ASSIGN.value and "plan" in run.result:
            plan = AssignPlanOut.model_validate(run.result["plan"])
        return RunOut(
            **_summary(run).model_dump(),
            brief=run.brief,
            steps=[RunStepOut.model_validate(s) for s in run.steps],
            result=run.result,
            error=run.error,
            course_status=course.status if course else None,
            plan=plan,
        )

    async def _sync(self, run: AgentRun) -> Course | None:
        """A run waiting for the expert finishes when the course is approved (or stops if it is archived)."""
        course = await self.session.get(Course, run.course_id) if run.course_id else None
        if course is None or run.status != RunStatus.WAITING.value or run.kind == RunKind.ASSIGN.value:
            return course
        key = "expert" if run.kind == RunKind.COURSE.value else "review"
        if course.status == CourseStatus.PUBLISHED.value and course.approved_at and course.approved_at >= run.created_at:
            approver = await self.session.get(User, course.approver_id) if course.approver_id else None
            who = approver.full_name if approver else "the expert"
            await StepLog(self.session, run).done(key, f"Approved by {who} on {course.approved_at:%d %b}. Learners can see it.")
            run.status, run.finished_at = RunStatus.DONE.value, utcnow()
        elif course.status == CourseStatus.ARCHIVED.value:
            await StepLog(self.session, run).skip(key, "The course was archived.")
            run.status, run.finished_at = RunStatus.CANCELLED.value, utcnow()
        return course

    # ---- start ------------------------------------------------------------------------------
    def _new_run(self, kind: RunKind, title: str, brief: dict[str, Any], actor: User, course_id: UUID | None) -> AgentRun:
        run = AgentRun(
            kind=kind.value,
            title=title[:200],
            brief=brief,
            steps=initial_steps(kind.value),
            result={},
            course_id=course_id,
            created_by_id=actor.id,
            engine=get_assistant().name,
        )
        self.session.add(run)
        return run

    async def start_course(self, data: CourseBriefIn, actor: User) -> AgentRun:
        if data.approver_id:
            expert = await self.session.get(User, data.approver_id)
            if expert is None or not expert.has_role("expert", "admin"):
                raise ValidationFailedError("Choose a subject expert to approve this course.")
        course = Course(
            title=data.topic.strip()[:200],
            skill_id=data.skill_id,
            kind=CourseKind.CERTIFICATION.value if data.certification else CourseKind.SELF_PACED.value,
            status=CourseStatus.DRAFTING.value,
            duration_minutes=data.duration_minutes,
            created_by_id=actor.id,
        )
        self.session.add(course)
        await self.session.flush()
        run = self._new_run(RunKind.COURSE, f"Course: {data.topic}", data.model_dump(mode="json"), actor, course.id)
        await self.session.flush()
        defer_job(self.session, Queues.AUTHORING, "agents.run", {"id": run.id})
        self.audit.record("helper.course_started", "agent_run", run.id, actor_id=actor.id, course_id=course.id)
        return run

    async def start_quiz(self, data: QuizBriefIn, actor: User) -> AgentRun:
        course = await CourseService(self.session).get(data.course_id)
        if course.status == CourseStatus.DRAFTING.value:
            raise ConflictError("The course is still being prepared. Please wait a moment.")
        if course.status == CourseStatus.ARCHIVED.value:
            raise ValidationFailedError("This course is archived.")
        if not quiz_writer.lesson_texts(await quiz_writer.course_lessons(self.session, course.id)):
            raise ValidationFailedError("Add lessons with text first; the questions are written from them.")
        busy = await self.session.scalar(
            select(func.count())
            .select_from(AgentRun)
            .where(AgentRun.course_id == course.id, AgentRun.status.in_([RunStatus.QUEUED.value, RunStatus.RUNNING.value]))
        )
        if busy:
            raise ConflictError("A helper is already working on this course.")
        run = self._new_run(RunKind.QUIZ, f"Quick check: {course.title}", data.model_dump(mode="json"), actor, course.id)
        await self.session.flush()
        defer_job(self.session, Queues.AUTHORING, "agents.run", {"id": run.id})
        self.audit.record("helper.quiz_started", "agent_run", run.id, actor_id=actor.id, course_id=course.id)
        return run

    # ---- worker -----------------------------------------------------------------------------
    async def execute(self, run_id: UUID) -> None:
        run = await self.session.get(AgentRun, run_id)
        if run is None or run.status != RunStatus.QUEUED.value:
            return  # already ran (a repeated job does nothing)
        run.status = RunStatus.RUNNING.value
        log = StepLog(self.session, run, live=True)
        await self.session.commit()
        try:
            if run.kind == RunKind.COURSE.value:
                await self._run_course(run, log)
            elif run.kind == RunKind.QUIZ.value:
                await self._run_quiz(run, log)
        except Exception as exc:
            logger.exception("Helper run %s failed", run_id)
            await self.session.rollback()
            run = await self.session.get(AgentRun, run_id, populate_existing=True)
            if run is None:
                return
            log = StepLog(self.session, run, live=False)
            message = exc.message if isinstance(exc, AppError) else "Something went wrong in this step."
            await log.fail_running(f"{message} Nothing was published. You can start again.")
            run.status, run.error, run.finished_at = RunStatus.FAILED.value, str(exc)[:500], utcnow()
            course = await self.session.get(Course, run.course_id) if run.course_id else None
            if course and course.status == CourseStatus.DRAFTING.value:
                course.status = CourseStatus.DRAFT.value  # never leave it stuck as "being prepared"
            await self._tell_creator(run, f"The helper could not finish: {run.title}")

    async def _run_course(self, run: AgentRun, log: StepLog) -> None:
        data = CourseBriefIn.model_validate(run.brief)
        course = await CourseService(self.session).get(run.course_id)  # type: ignore[arg-type]
        brief = CourseBrief(data.topic, data.audience, data.goal, data.duration_minutes)
        assistant = get_assistant()

        await log.done("brief", f"{data.topic} for {data.audience}, about {data.duration_minutes} minutes. Goal: {data.goal}")

        await log.start("material")
        passages: list[Passage] = []
        if data.use_knowledge and await SettingsService(self.session).get("learning.helper_use_knowledge"):
            passages = await find_material(self.session, data.topic, data.goal)
            run.result = {**run.result, "sources": [{"id": str(p.item_id), "title": p.title} for p in passages]}
            detail = (
                f"Used {len(passages)} company item{'s' if len(passages) != 1 else ''}: " + ", ".join(p.title for p in passages)
                if passages
                else "No matching company items, so the content is written from the brief."
            )
            await log.done("material", detail)
        else:
            await log.skip("material", "Not asked to use company material.")

        await log.start("outline")
        plan = await assistant.plan_course(brief, passages)
        outline = "; ".join(f"{m.title} ({m.outcome})" for m in plan.modules)
        await log.done("outline", f"{len(plan.modules)} modules: {outline}")

        await log.start("content")
        minutes = max(3, data.duration_minutes // max(1, len(plan.modules)))
        lessons: list[Lesson] = []
        for position, module in enumerate(plan.modules, start=1):
            content = await assistant.write_module(brief, module, passages)
            body = content.body + (f"\n\n{content.example}" if content.example else "")
            lesson = Lesson(
                course_id=course.id,
                position=position,
                title=module.title[:200],
                kind=LessonKind.READING.value,
                summary=module.outcome,
                body=body,
                source_ref=(content.source_ref or None),
                duration_minutes=minutes,
            )
            self.session.add(lesson)
            lessons.append(lesson)
        course.title = plan.title[:200]
        course.description = plan.description
        course.duration_minutes = minutes * len(lessons)
        await self.session.flush()
        words = sum(len(lsn.body.split()) for lsn in lessons)
        await log.done("content", f"{len(lessons)} modules written ({words} words), each with a workplace example.")

        await log.start("resources")
        added = _attach_links(lessons, data.links, passages)
        await self.session.flush()
        if added:
            await log.done("resources", f"Added {added} link{'s' if added != 1 else ''} to the matching modules.")
        else:
            await log.skip("resources", "No links were given and no company material matched.")

        if data.write_quiz:
            await log.start("quiz")
            if data.certification:
                course.pass_mark = 80
            plan_q = await quiz_writer.plan_quiz(self.session, course)
            summary, _ = await quiz_writer.write_for_course(self.session, course, plan_q)
            await log.done("quiz", summary)
        else:
            await log.skip("quiz", "Not asked for a quick check. You can add one later.")

        await log.start("check")
        issues = check_course(lessons, data.duration_minutes)
        await log.done("check", "No problems found." if not issues else "Worth a look: " + " ".join(issues))

        await log.start("trial")
        questions = await CourseService(self.session).questions(course.id)
        pass_mark = course.pass_mark or int(await SettingsService(self.session).get("learning.quiz_pass_mark"))
        _, detail = trial_run(lessons, list(questions), pass_mark)
        await log.done("trial", detail)

        course.status = CourseStatus.DRAFT.value
        await self.session.flush()
        run.result = {**run.result, "course_id": str(course.id), "lessons": len(lessons), "questions": len(questions)}
        await self._hand_to_expert(run, course, data.approver_id, log)

    async def _hand_to_expert(self, run: AgentRun, course: Course, approver_id: UUID | None, log: StepLog) -> None:
        creator = await self.session.get(User, run.created_by_id) if run.created_by_id else None
        key = "expert" if run.kind == RunKind.COURSE.value else "review"
        approver_id = approver_id or course.approver_id
        if approver_id and creator and course.status != CourseStatus.IN_REVIEW.value:
            await CourseService(self.session).submit_for_review(course.id, approver_id, creator)
        if approver_id:
            expert = await self.session.get(User, approver_id)
            name = expert.full_name if expert else "the expert"
            await log.wait(key, f"Waiting for {name} to approve. Nothing is published until then.")
        else:
            await log.wait(key, "Open the course, check it, and send it to a subject expert to approve.")
        run.status = RunStatus.WAITING.value
        await self._tell_creator(run, f"Ready to check: {course.title}")

    async def _run_quiz(self, run: AgentRun, log: StepLog) -> None:
        data = QuizBriefIn.model_validate(run.brief)
        course = await CourseService(self.session).get(data.course_id)

        await log.start("content")
        lessons = await quiz_writer.course_lessons(self.session, course.id)
        texts = quiz_writer.lesson_texts(lessons)
        goals = [lsn.summary for lsn in lessons if lsn.summary]
        read = f"{len(texts)} lessons read."
        await log.done("content", f"{read} Goals: " + "; ".join(goals[:4]) if goals else read)

        plan = await quiz_writer.plan_quiz(
            self.session,
            course,
            choice_count=data.choice_count,
            written_count=data.written_count,
            pass_mark=data.pass_mark,
            time_limit=data.time_limit_minutes,
        )
        await log.start("draft")
        drafts = await quiz_writer.draft(course, lessons, plan)
        written = sum(1 for q in drafts if q.kind == "written")
        choice = len(drafts) - written
        await log.done("draft", f"Drafted {choice} multiple choice and {written} written questions, each with its answer.")

        await log.done("settings", f"Pass mark {plan.pass_mark} out of 100. Time limit {plan.time_limit} minutes.")

        await log.start("check")
        checked = check_questions(drafts)
        if not checked.kept:
            raise ValidationFailedError("No usable questions could be written from this course.")
        await log.done("check", quiz_writer.describe_check(checked.kept, checked.removed))

        await log.start("save")
        was_live = course.status == CourseStatus.PUBLISHED.value
        saved = await quiz_writer.save(self.session, course, checked.kept, plan)
        note = " The course was live, so it goes back to the expert first." if was_live else ""
        await log.done("save", f"{len(saved)} questions saved to the course; the old ones were replaced.{note}")

        await log.start("trial")
        _, detail = trial_run(lessons, saved, plan.pass_mark)
        await log.done("trial", detail)
        run.result = {**run.result, "questions": len(saved), "pass_mark": plan.pass_mark, "time_limit": plan.time_limit}
        await self._hand_to_expert(run, course, None, log)

    async def _tell_creator(self, run: AgentRun, title: str) -> None:
        if run.created_by_id:
            await NotificationService(self.session).notify(
                run.created_by_id,
                kind=NotificationKind.SYSTEM,
                title=title,
                link=f"/admin/helpers/{run.id}",
                related=("agent_run", run.id),
            )

    # ---- assignment helper ------------------------------------------------------------------
    async def plan_assign(self, data: AssignRequestIn, actor: User) -> AgentRun:
        run = self._new_run(RunKind.ASSIGN, f"Assign: {data.text}", data.model_dump(), actor, None)
        log = StepLog(self.session, run)
        courses = (
            await self.session.scalars(select(Course).where(Course.status == CourseStatus.PUBLISHED.value).order_by(Course.title))
        ).all()
        departments = (await self.session.scalars(select(Department).order_by(Department.name))).all()
        roles = (await self.session.scalars(select(JobRole).order_by(JobRole.name))).all()
        request = await get_assistant().read_request(
            data.text,
            courses=[c.title for c in courses],
            departments=[d.name for d in departments],
            roles=[r.name for r in roles],
            today=today().isoformat(),
        )
        course = next((c for c in courses if c.title == request.course), None)
        audience: Audience | None = None
        if request.everyone:
            audience = Audience(everyone=True)
        elif dept := next((d for d in departments if d.name == request.department), None):
            audience = Audience(department_id=dept.id)
        elif role := next((r for r in roles if r.name == request.job_role), None):
            audience = Audience(job_role_id=role.id)
        missing = [m for m, ok in (("course", course), ("who", audience)) if not ok]
        read = [
            f"Course: {course.title}" if course else "Course: not clear",
            f"Who: {_who(request)}" if audience else "Who: not clear",
        ]
        await log.done("read", ". ".join(read) + ".")

        due_from_request = _valid_date(request.due_on) is not None
        default_days = int(await SettingsService(self.session).get("learning.default_due_days"))
        due = _valid_date(request.due_on) or today() + timedelta(days=default_days)
        if due < today():
            due, due_from_request = today() + timedelta(days=7), False
        why = "." if due_from_request else " (the request gave no date, so the usual period is used)."
        await log.done("due", f"Due {due:%d %b %Y}{why}")

        plan = AssignPlanOut(
            course_id=course.id if course else None,
            course_title=course.title if course else None,
            audience=audience.model_dump(mode="json") if audience else None,
            audience_label=None,
            due_on=due,
            due_from_request=due_from_request,
            missing=missing,
        )
        if course and audience:
            preview = await AssignmentService(self.session).preview(AssignIn(course_id=course.id, audience=audience, due_on=due))
            plan.preview, plan.audience_label = preview, preview.audience_label
            await log.done("who", f"{preview.new_people} people will get it; {preview.already_assigned} already have it.")
        else:
            wanted = " and ".join("course" if m == "course" else "people" for m in missing)
            await log.wait("who", f"Choose the {wanted} below.")
        await log.wait("confirm", "Check the list and press Assign. Nothing is sent before that.")
        run.status = RunStatus.WAITING.value
        run.result = {"plan": plan.model_dump(mode="json")}
        await self.session.flush()
        self.audit.record("helper.assign_planned", "agent_run", run.id, actor_id=actor.id, text=data.text)
        return run

    async def confirm_assign(self, run_id: UUID, data: AssignConfirmIn, actor: User) -> AgentRun:
        run = await self.get_run(run_id)
        if run.kind != RunKind.ASSIGN.value or run.status != RunStatus.WAITING.value:
            raise ConflictError("This request was already handled.")
        log = StepLog(self.session, run)
        service = AssignmentService(self.session)
        request = AssignIn(course_id=data.course_id, audience=data.audience, due_on=data.due_on, is_mandatory=data.is_mandatory)
        preview = await service.preview(request)
        await log.done("who", f"{preview.audience_label}: {preview.new_people} new, {preview.already_assigned} already assigned.")
        await log.done("confirm", f"Confirmed by {actor.full_name}.")
        result = await service.assign(request, actor)
        await self.session.flush()
        await log.done("assign", f"{result.count} people assigned to {preview.course_title}; each got a notice with the link.")

        course = await CourseService(self.session).get(data.course_id)
        seen = await self.session.scalar(
            select(func.count()).select_from(Assignment).where(Assignment.batch_id == result.bulk_action_id)
        )
        if course.status == CourseStatus.PUBLISHED.value and seen == result.count:
            await log.done("visible", f"Checked: it shows on the Learn page of all {seen} people.")
        else:
            await log.done("visible", f"Only {seen} of {result.count} could be confirmed; check the tracker.")
        due = f"due {data.due_on:%d %b}" if data.due_on else "no due date"
        await log.done("tracker", f"Recorded with {due}. Reminders go 7 and 2 days before and on the day.")
        run.status, run.finished_at, run.course_id = RunStatus.DONE.value, utcnow(), course.id
        run.result = {
            **run.result,
            "bulk_action_id": str(result.bulk_action_id),
            "count": result.count,
            "undo_until": result.undo_until.isoformat(),
            "course_id": str(course.id),
        }
        self.audit.record("helper.assign_confirmed", "agent_run", run.id, actor_id=actor.id, count=result.count)
        return run

    async def cancel(self, run_id: UUID, actor: User) -> AgentRun:
        run = await self.get_run(run_id)
        if run.status not in {RunStatus.WAITING.value, RunStatus.QUEUED.value} or run.kind != RunKind.ASSIGN.value:
            raise ConflictError("Only a request waiting for your go-ahead can be cancelled.")
        log = StepLog(self.session, run)
        for step in run.steps:
            if step["status"] in {"pending", "waiting"}:
                await log.skip(step["key"], "Cancelled.")
        run.status, run.finished_at = RunStatus.CANCELLED.value, utcnow()
        self.audit.record("helper.cancelled", "agent_run", run.id, actor_id=actor.id)
        return run


def _summary(run: AgentRun) -> RunSummaryOut:
    return RunSummaryOut(
        id=run.id,
        kind=run.kind,
        status=run.status,
        title=run.title,
        course_id=run.course_id,
        created_at=run.created_at,
        finished_at=run.finished_at,
        step_done=sum(1 for s in run.steps if s["status"] in {"done", "skipped"}),
        step_total=len(run.steps),
    )


def _who(request: Any) -> str:
    if request.everyone:
        return "everyone"
    return f"department {request.department}" if request.department else f"role {request.job_role}"


def _valid_date(value: str | None) -> date | None:
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def _attach_links(lessons: list[Lesson], links: list[str], passages: list[Passage]) -> int:
    """Put each link in the module it fits best (by words in the link), else the last module."""
    if not lessons:
        return 0
    added = 0
    for link in links:
        words = {w for w in link.lower().replace("-", "/").replace("_", "/").split("/") if len(w) > 3}
        target = max(lessons, key=lambda lsn: len(words & set(lsn.title.lower().split())))
        if not words & set(target.title.lower().split()):
            target = lessons[-1]
        target.body += f"\n\nWatch or read more: {link}"
        added += 1
    if passages:
        # Named, not linked: most learners cannot open the Knowledge Hub.
        refs = "\n".join(f"- {p.title} (Knowledge Hub)" for p in passages)
        lessons[-1].body += f"\n\nCompany material used in this course:\n{refs}"
        added += len(passages)
    return added
