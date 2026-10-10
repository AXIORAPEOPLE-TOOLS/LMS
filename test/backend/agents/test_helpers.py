"""Helpers for the HR steps of LMS.pdf: course from a brief, quiz writer, assignment from a request.

Every run shows each step, and people approve: nothing is published or sent without a person.
"""

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.agents.models import AgentRun
from app.modules.ai.provider import CourseBrief, Passage
from app.modules.ai.rules_provider import RulesProvider
from app.modules.ai.service import set_assistant
from app.modules.identity.models import Department
from app.modules.knowledge.models import KnowledgeItem
from app.modules.learning.models import Assignment, Course, CourseQuestion, Lesson
from app.modules.notifications.models import Notification
from app.shared import clock
from testkit import UserFactory, auth

REFUND_SOP = (
    "Refund requests must be logged in the ticket system within one hour. "
    "Check the order number and the payment method before approving a refund. "
    "Refunds above 5000 rupees need approval from the team lead. "
    "Always tell the customer the refund reference number and the expected date. "
    "Close the ticket only after the customer confirms the refund."
)


async def _course_with_text(session: AsyncSession, *, status: str = "published") -> Course:
    course = Course(title="Refund handling", status=status)
    session.add(course)
    await session.flush()
    for i, (title, body) in enumerate(
        [
            ("Logging a refund", REFUND_SOP),
            ("Talking to the customer", "Always tell the customer the refund reference number. Be polite and give a date."),
        ],
        start=1,
    ):
        session.add(Lesson(course_id=course.id, position=i, title=title, summary=f"Do {title.lower()}", body=body))
    await session.commit()
    return course


def _steps(run: dict[str, Any]) -> dict[str, str]:
    return {s["key"]: s["status"] for s in run["steps"]}


async def test_course_from_a_brief_runs_every_step_and_waits_for_the_expert(
    client: AsyncClient, session: AsyncSession, make_user: UserFactory
) -> None:
    session.add(KnowledgeItem(title="Refund process SOP", body=REFUND_SOP))
    await session.commit()
    admin = await make_user("admin")
    expert = await make_user("expert", full_name="Esha Expert")
    brief = {
        "topic": "Refund process",
        "audience": "Customer support staff",
        "goal": "Handle refund requests correctly and on time",
        "duration_minutes": 30,
        "approver_id": str(expert.id),
        "links": ["https://example.com/videos/refund-steps"],
    }
    response = await client.post("/admin/helpers/course", json=brief, headers=auth(admin))
    assert response.status_code == 202, response.text
    run = (await client.get(f"/admin/helpers/runs/{response.json()['id']}", headers=auth(admin))).json()

    assert run["status"] == "waiting" and run["kind"] == "course"
    steps = _steps(run)
    assert all(steps[k] == "done" for k in ("brief", "material", "outline", "content", "resources", "quiz", "check", "trial"))
    assert steps["expert"] == "waiting" and "Esha Expert" in run["steps"][-1]["detail"]
    assert run["result"]["sources"][0]["title"] == "Refund process SOP"  # company material was used
    assert run["course_status"] == "in_review"  # nothing is published until the expert approves

    course_id = run["course_id"]
    detail = (await client.get(f"/admin/courses/{course_id}", headers=auth(admin))).json()
    assert len(detail["lessons"]) == 3 and all(lsn["body"] for lsn in detail["lessons"])
    assert any("refund-steps" in lsn["body"] for lsn in detail["lessons"])  # the link landed in a module
    kinds = {q["kind"] for q in detail["questions"]}
    assert kinds == {"choice", "written"} and detail["quiz_time_limit_minutes"]

    await client.post(f"/admin/courses/{course_id}/review", json={"approve": True, "note": ""}, headers=auth(expert))
    run = (await client.get(f"/admin/helpers/runs/{run['id']}", headers=auth(admin))).json()
    assert run["status"] == "done" and _steps(run)["expert"] == "done"


async def test_a_failing_step_is_shown_and_the_course_is_not_left_half_made(
    client: AsyncClient, session: AsyncSession, make_user: UserFactory
) -> None:
    class Broken(RulesProvider):
        async def plan_course(self, brief: CourseBrief, passages: list[Passage]) -> Any:
            raise RuntimeError("model went away")

    set_assistant(Broken())
    admin = await make_user("admin")
    brief = {"topic": "Fire safety", "audience": "All staff", "goal": "Know the exits", "use_knowledge": False}
    run = (await client.post("/admin/helpers/course", json=brief, headers=auth(admin))).json()
    run = (await client.get(f"/admin/helpers/runs/{run['id']}", headers=auth(admin))).json()
    assert run["status"] == "failed"
    assert _steps(run)["outline"] == "failed" and "Nothing was published" in run["steps"][2]["detail"]
    assert run["course_status"] == "draft"  # never stuck as "being prepared"


async def test_quiz_writer_drafts_checks_and_saves_with_pass_mark_and_time(
    client: AsyncClient, session: AsyncSession, make_user: UserFactory
) -> None:
    admin = await make_user("admin")
    course = await _course_with_text(session)
    response = await client.post(
        "/admin/helpers/quiz", json={"course_id": str(course.id), "choice_count": 3, "written_count": 1}, headers=auth(admin)
    )
    assert response.status_code == 202, response.text
    run = (await client.get(f"/admin/helpers/runs/{response.json()['id']}", headers=auth(admin))).json()
    steps = _steps(run)
    assert all(steps[k] == "done" for k in ("content", "draft", "settings", "check", "save", "trial"))
    assert steps["review"] == "waiting" and run["status"] == "waiting"

    course_id = course.id
    session.expire_all()
    questions = (await session.scalars(select(CourseQuestion).where(CourseQuestion.course_id == course_id))).all()
    assert any(q.kind == "written" and q.rubric for q in questions)
    assert all(0 <= q.answer_index < len(q.options) for q in questions if q.kind == "choice")
    fresh = await session.get(Course, course_id)
    assert fresh is not None and fresh.pass_mark == 60 and fresh.quiz_time_limit_minutes
    assert fresh.status == "draft"  # a live course with new questions goes back for approval


async def test_quiz_writer_needs_lesson_text(client: AsyncClient, session: AsyncSession, make_user: UserFactory) -> None:
    admin = await make_user("admin")
    course = Course(title="Empty", status="draft")
    session.add(course)
    await session.commit()
    response = await client.post("/admin/helpers/quiz", json={"course_id": str(course.id)}, headers=auth(admin))
    assert response.status_code == 422 and "lessons" in response.json()["error"]["message"]


async def test_assign_from_a_request_previews_then_assigns_only_after_confirm(
    client: AsyncClient, session: AsyncSession, make_user: UserFactory
) -> None:
    clock.freeze(datetime(2026, 10, 10, 9, tzinfo=timezone.utc))
    sales = Department(name="Sales")
    session.add(sales)
    await session.commit()
    admin = await make_user("admin")
    people = [await make_user(department_id=sales.id) for _ in range(2)]
    await make_user()  # someone outside Sales
    course = await _course_with_text(session)

    text = "Please assign Refund handling to Sales by 30 Nov"
    run = (await client.post("/admin/helpers/assign", json={"text": text}, headers=auth(admin))).json()
    assert run["status"] == "waiting" and run["plan"]["course_title"] == "Refund handling"
    assert run["plan"]["due_on"] == "2026-11-30" and run["plan"]["due_from_request"] is True
    assert run["plan"]["preview"]["new_people"] == 2 and _steps(run)["confirm"] == "waiting"
    assert await session.scalar(select(func.count()).select_from(Assignment)) == 0  # nothing sent yet

    body = {"course_id": str(course.id), "audience": run["plan"]["audience"], "due_on": run["plan"]["due_on"]}
    done = (await client.post(f"/admin/helpers/runs/{run['id']}/confirm", json=body, headers=auth(admin))).json()
    assert done["status"] == "done" and done["result"]["count"] == 2 and done["result"]["bulk_action_id"]
    assert all(v == "done" for v in _steps(done).values())
    assigned = set((await session.scalars(select(Assignment.user_id))).all())
    assert assigned == {p.id for p in people}
    notes = await session.scalar(select(func.count()).select_from(Notification).where(Notification.user_id.in_(assigned)))
    assert notes == 2

    again = await client.post(f"/admin/helpers/runs/{run['id']}/confirm", json=body, headers=auth(admin))
    assert again.status_code == 409


async def test_unclear_request_asks_for_the_missing_parts_and_can_be_cancelled(
    client: AsyncClient, session: AsyncSession, make_user: UserFactory
) -> None:
    admin = await make_user("admin")
    run = (await client.post("/admin/helpers/assign", json={"text": "something for the new joiners"}, headers=auth(admin))).json()
    assert set(run["plan"]["missing"]) == {"course", "who"} and run["plan"]["preview"] is None
    assert run["plan"]["due_from_request"] is False  # the usual period from settings is used
    cancelled = (await client.post(f"/admin/helpers/runs/{run['id']}/cancel", headers=auth(admin))).json()
    assert cancelled["status"] == "cancelled"
    listing = (await client.get("/admin/helpers/runs", headers=auth(admin))).json()
    assert listing[0]["id"] == run["id"]


async def test_helpers_are_for_admins_only(client: AsyncClient, make_user: UserFactory) -> None:
    learner = await make_user()
    assert (await client.get("/admin/helpers/runs", headers=auth(learner))).status_code == 403


async def test_a_repeated_job_does_nothing(client: AsyncClient, session: AsyncSession, make_user: UserFactory) -> None:
    from app.core.queue import run_job

    admin = await make_user("admin")
    course = await _course_with_text(session, status="draft")
    run = (await client.post("/admin/helpers/quiz", json={"course_id": str(course.id)}, headers=auth(admin))).json()
    before = await session.scalar(select(func.count()).select_from(CourseQuestion))
    await run_job("agents.run", {"id": run["id"]})
    session.expire_all()
    assert await session.scalar(select(func.count()).select_from(CourseQuestion)) == before
    assert (await session.get(AgentRun, UUID(run["id"]))) is not None
