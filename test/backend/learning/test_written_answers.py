"""Written answers scored against a rubric; a person checks unsure scores before the result counts (golden rule 5)."""

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.learning.models import Assignment, Course, CourseQuestion, Lesson
from testkit import UserFactory, auth

RUBRIC = [{"point": "log the refund in the ticket system", "marks": 2}, {"point": "team lead approves big refunds", "marks": 1}]


async def _course(session: AsyncSession, approver_id: object = None) -> tuple[Course, CourseQuestion, CourseQuestion]:
    course = Course(title="Refunds", status="published", pass_mark=60, approver_id=approver_id)
    session.add(course)
    await session.flush()
    session.add(Lesson(course_id=course.id, position=1, title="Refunds", body="text"))
    choice = CourseQuestion(course_id=course.id, position=1, text="Pick one", options=["right", "wrong"], answer_index=0)
    written = CourseQuestion(
        course_id=course.id, position=2, text="What do you do with a refund?", options=[], answer_index=0,
        kind="written", model_answer="Log it; big ones need the team lead.", rubric=RUBRIC,
    )
    session.add_all([choice, written])
    await session.commit()
    return course, choice, written


async def test_learner_sees_written_question_without_the_rubric(client: AsyncClient, session: AsyncSession, make_user: UserFactory) -> None:
    course, _, written = await _course(session)
    learner = await make_user()
    quiz = (await client.get(f"/courses/{course.id}/quiz", headers=auth(learner))).json()
    shown = next(q for q in quiz if q["id"] == str(written.id))
    assert shown["kind"] == "written" and "rubric" not in shown and "model_answer" not in shown


async def test_clear_written_answer_is_scored_at_once(client: AsyncClient, session: AsyncSession, make_user: UserFactory) -> None:
    course, choice, written = await _course(session)
    learner = await make_user()
    answers = {
        str(choice.id): 0,
        str(written.id): "I log the refund in the ticket system and the team lead approves big refunds.",
    }
    result = (await client.post(f"/courses/{course.id}/quiz", json={"answers": answers}, headers=auth(learner))).json()
    assert result["under_review"] is False and result["score"] == 100 and result["passed"] is True
    marks = next(r for r in result["results"] if r["question_id"] == str(written.id))
    assert marks["marks"] == 3 and marks["max_marks"] == 3


async def test_unsure_score_waits_for_a_person_then_counts(client: AsyncClient, session: AsyncSession, make_user: UserFactory) -> None:
    expert = await make_user("expert")
    course, choice, written = await _course(session, approver_id=expert.id)
    learner = await make_user()
    lessons = (await client.get(f"/courses/{course.id}", headers=auth(learner))).json()["lessons"]
    await client.post(f"/lessons/{lessons[0]['id']}/complete", headers=auth(learner))
    answers = {str(choice.id): 0, str(written.id): "refund ticket"}
    result = (await client.post(f"/courses/{course.id}/quiz", json={"answers": answers}, headers=auth(learner))).json()
    assert result["under_review"] is True and result["passed"] is False and result["can_retake"] is False
    again = await client.post(f"/courses/{course.id}/quiz", json={"answers": answers}, headers=auth(learner))
    assert again.status_code == 409  # no retake while a person is checking

    other_expert = await make_user("expert")
    assert (await client.get("/admin/written-answers", headers=auth(other_expert))).json() == []  # only the course expert
    queue = (await client.get("/admin/written-answers", headers=auth(expert))).json()
    assert len(queue) == 1 and queue[0]["answers"][0]["answer"] == "refund ticket"
    attempt_id = queue[0]["attempt_id"]

    too_many = {"marks": [{"question_id": str(written.id), "marks": 9}]}
    assert (await client.post(f"/admin/written-answers/{attempt_id}", json=too_many, headers=auth(expert))).status_code == 422
    decision = {"marks": [{"question_id": str(written.id), "marks": 2, "feedback": "Good start; mention the team lead."}]}
    checked = await client.post(f"/admin/written-answers/{attempt_id}", json=decision, headers=auth(expert))
    assert checked.status_code == 200 and checked.json()["provisional_score"] == 75  # (1 + 2) of 4 marks
    assert (await client.get("/admin/written-answers", headers=auth(expert))).json() == []

    course_id = course.id
    session.expire_all()
    assignment = (await session.scalars(select(Assignment).where(Assignment.user_id == learner.id))).one()
    assert assignment.quiz_score == 75 and assignment.status == "completed"
    attempts = (await client.get(f"/courses/{course_id}/quiz/attempts", headers=auth(learner))).json()
    assert attempts[0]["review_status"] == "done" and attempts[0]["passed"] is True
