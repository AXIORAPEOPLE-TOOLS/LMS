from uuid import UUID

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.learning.models import Course
from testkit import UserFactory, auth, make_course


async def test_catalogue_only_lists_published(client: AsyncClient, session: AsyncSession, make_user: UserFactory) -> None:
    await make_course(session, "Live course")
    await make_course(session, "Hidden draft", status="draft")
    user = await make_user()
    titles = [c["title"] for c in (await client.get("/courses", headers=auth(user))).json()]
    assert titles == ["Live course"]


async def test_full_course_flow_completes_and_shows_progress(
    client: AsyncClient, session: AsyncSession, make_user: UserFactory
) -> None:
    course = await make_course(session, lessons=2, questions=2)
    user = await make_user()
    h = auth(user)
    detail = (await client.get(f"/courses/{course.id}", headers=h)).json()
    assert "answer_index" not in str(detail)  # learners never see answers
    lesson_ids = [lsn["id"] for lsn in detail["lessons"]]

    first = (await client.post(f"/lessons/{lesson_ids[0]}/complete", headers=h)).json()
    assert first["progress_pct"] == 33 and first["next_lesson_id"] == lesson_ids[1]
    second = (await client.post(f"/lessons/{lesson_ids[1]}/complete", headers=h)).json()
    assert second["quiz_pending"] is True and second["course_completed"] is False

    quiz = (await client.get(f"/courses/{course.id}/quiz", headers=h)).json()
    assert len(quiz) == 2 and "answer_index" not in quiz[0]  # learners get questions, never answers
    questions = [q["id"] for q in quiz]
    wrong = {q: 1 for q in questions}
    failed = (await client.post(f"/courses/{course.id}/quiz", json={"answers": wrong}, headers=h)).json()
    assert failed["passed"] is False and failed["correct_count"] == 0 and failed["total"] == 2
    assert failed["results"][0]["right_index"] is None and failed["results"][0]["reason"] is None  # no answers before a pass
    assert failed["can_retake"] is True and failed["attempts_used"] == 1 and failed["attempts_left"] == 2
    right = {q: 0 for q in questions}
    passed = (await client.post(f"/courses/{course.id}/quiz", json={"answers": right}, headers=h)).json()
    assert passed["passed"] is True and passed["course_completed"] is True
    assert passed["results"][0]["right_index"] == 0 and passed["can_retake"] is False

    mine = (await client.get("/me/assignments", headers=h)).json()
    assert mine[0]["status"] == "completed" and mine[0]["source"] == "self"


async def test_simulation_checks_order(client: AsyncClient, session: AsyncSession, make_user: UserFactory) -> None:
    course = await make_course(session, lessons=0, questions=0, simulation=True)
    user = await make_user()
    sim = (await client.get(f"/courses/{course.id}", headers=auth(user))).json()["lessons"][0]
    url = f"/lessons/{sim['id']}/simulation"
    wrong = (await client.post(url, json={"order": ["b", "a"]}, headers=auth(user))).json()
    assert wrong["correct"] is False and wrong["first_wrong_step"] == 0 and "Sanitiser" in wrong["message"]
    right = (await client.post(url, json={"order": ["a", "b"]}, headers=auth(user))).json()
    assert right["correct"] is True and right["points"] > 0


SOP = (
    "Why refunds matter\nRefunds keep customer trust when something goes wrong with an order.\n\n"
    "Check eligibility\nRefunds are allowed within seven days of delivery for every customer order.\n\n"
    "Process the refund\nApprove refunds up to five thousand rupees yourself and ask the team lead above that.\n"
) * 3


async def test_course_builder_drafts_from_document_and_needs_expert_approval(
    client: AsyncClient, session: AsyncSession, make_user: UserFactory
) -> None:
    admin = await make_user("admin")
    expert = await make_user("expert")
    response = await client.post(
        "/admin/courses/drafts",
        files={"file": ("Refund_SOP_v3.txt", SOP.encode(), "text/plain")},
        data={"options": '{"simulation": true, "quiz_size": 3}'},
        headers=auth(admin),
    )
    assert response.status_code == 202
    course_id = response.json()["id"]
    draft = (await client.get(f"/admin/courses/{course_id}", headers=auth(admin))).json()
    assert draft["status"] == "draft"  # the inline queue finished the drafting job
    assert draft["lessons"][-1]["kind"] == "simulation"
    assert draft["lessons"][0]["source_ref"].startswith("Source p.")
    assert len(draft["questions"]) >= 1

    # Nothing is published until an expert approves.
    learner = await make_user()
    assert (await client.get(f"/courses/{course_id}", headers=auth(learner))).status_code == 404
    submit = f"/admin/courses/{course_id}/submit"
    assert (await client.post(submit, json={"approver_id": str(learner.id)}, headers=auth(admin))).status_code == 422
    await client.post(submit, json={"approver_id": str(expert.id)}, headers=auth(admin))
    inbox = (await client.get("/me/notifications", headers=auth(expert))).json()["items"]
    assert any("Please check the course" in n["title"] for n in inbox)
    ok = await client.post(f"/admin/courses/{course_id}/review", json={"approve": True}, headers=auth(expert))
    assert ok.status_code == 204
    status = (await session.scalars(select(Course.status).where(Course.id == UUID(course_id)))).one()
    assert status == "published"


async def test_unreadable_upload_is_rejected(client: AsyncClient, make_user: UserFactory) -> None:
    admin = await make_user("admin")
    response = await client.post(
        "/admin/courses/drafts", files={"file": ("x.exe", b"MZ", "application/octet-stream")}, headers=auth(admin)
    )
    assert response.status_code == 422


async def test_quiz_tries_are_limited_by_settings(client: AsyncClient, session: AsyncSession, make_user: UserFactory) -> None:
    course = await make_course(session, lessons=0, questions=2)
    h = auth(await make_user())
    questions = [q["id"] for q in (await client.get(f"/courses/{course.id}/quiz", headers=h)).json()]
    wrong = {q: 1 for q in questions}
    for left in (2, 1, 0):
        result = (await client.post(f"/courses/{course.id}/quiz", json={"answers": wrong}, headers=h)).json()
        assert result["attempts_left"] == left and result["can_retake"] is (left > 0)
    blocked = await client.post(f"/courses/{course.id}/quiz", json={"answers": wrong}, headers=h)
    assert blocked.status_code == 409 and "3 tries" in blocked.json()["error"]["message"]
