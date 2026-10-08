from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.models import Department
from app.modules.learning.models import Assignment
from app.modules.reports.base import REPORTS
from app.shared import clock
from testkit import UserFactory, auth, make_course, make_role, make_skill


async def _compliance_data(session: AsyncSession, make_user: UserFactory):  # type: ignore[no-untyped-def]
    support = Department(name="Support")
    admissions = Department(name="Admissions")
    session.add_all([support, admissions])
    await session.commit()
    manager = await make_user("manager")
    course = await make_course(session, "POSH awareness", is_mandatory=True)
    past = clock.today() - timedelta(days=5)
    on_time = await make_user(full_name="Riya Sharma", department_id=admissions.id)
    late = await make_user(full_name="Dev Patel", department_id=support.id, manager_id=manager.id)
    session.add_all([
        Assignment(user_id=on_time.id, course_id=course.id, is_mandatory=True, due_on=past, status="completed",
                   completed_at=datetime.now(UTC) - timedelta(days=7)),
        Assignment(user_id=late.id, course_id=course.id, is_mandatory=True, due_on=past),
    ])
    await session.commit()
    return manager


async def test_catalogue_groups_reports(client: AsyncClient, make_user: UserFactory) -> None:
    admin = await make_user("admin")
    manager = await make_user("manager")
    groups = (await client.get("/reports", headers=auth(admin))).json()
    assert [g["group"] for g in groups][0] == "Skills and tests"
    assert sum(len(g["reports"]) for g in groups) == len(REPORTS)
    manager_ids = {r["id"] for g in (await client.get("/reports", headers=auth(manager))).json() for r in g["reports"]}
    assert "audit_log" not in manager_ids  # admin-only report hidden
    learner = await make_user()
    assert (await client.get("/reports", headers=auth(learner))).status_code == 403


async def test_compliance_report_drilldown_and_exports(client: AsyncClient, session: AsyncSession, make_user: UserFactory) -> None:
    manager = await _compliance_data(session, make_user)
    admin = await make_user("admin", full_name="Ada Admin")
    h = auth(admin)
    report = (await client.get("/reports/mandatory_compliance", headers=h)).json()
    rows = {r["department"]: r for r in report["rows"]}
    assert rows["Admissions"]["on_time_pct"] == 100 and rows["Support"]["overdue"] == 1
    assert report["scope"] == "company"

    people = (await client.get("/reports/mandatory_compliance/drill?row=Support&column=overdue", headers=h)).json()
    assert people == [{"person": "Dev Patel", "course": "POSH awareness", "due_on": people[0]["due_on"], "status": "overdue"}]

    for fmt, magic in (("csv", b"\xef\xbb\xbf"), ("xlsx", b"PK"), ("pdf", b"%PDF")):
        response = await client.get(f"/reports/mandatory_compliance/export?format={fmt}", headers=h)
        assert response.status_code == 200 and response.content.startswith(magic)
        assert "attachment" in response.headers["content-disposition"]
    csv_text = (await client.get("/reports/mandatory_compliance/export?format=csv", headers=h)).content.decode("utf-8-sig")
    assert "Exported by Ada Admin" in csv_text.splitlines()[0]
    audit = (await client.get("/audit?action=report.exported", headers=h)).json()
    assert len(audit) == 4

    # Managers only see their own team.
    team = (await client.get("/reports/mandatory_compliance", headers=auth(manager))).json()
    assert team["scope"] == "team" and [r["department"] for r in team["rows"]] == ["Support"]


async def test_every_report_runs_on_empty_and_filled_data(client: AsyncClient, session: AsyncSession, make_user: UserFactory) -> None:
    admin = await make_user("admin")
    for report_id in REPORTS:
        response = await client.get(f"/reports/{report_id}?period=month", headers=auth(admin))
        assert response.status_code == 200, report_id
    await _compliance_data(session, make_user)
    for report_id in REPORTS:
        assert (await client.get(f"/reports/{report_id}", headers=auth(admin))).status_code == 200, report_id


async def test_schedule_a_report(client: AsyncClient, make_user: UserFactory) -> None:
    admin = await make_user("admin")
    created = await client.post("/reports/course_completion/schedule", json={"frequency": "weekly", "format": "pdf"},
                                headers=auth(admin))
    assert created.status_code == 201
    assert len((await client.get("/reports/schedules", headers=auth(admin))).json()) == 1


async def test_admin_home_numbers(client: AsyncClient, session: AsyncSession, make_user: UserFactory) -> None:
    await _compliance_data(session, make_user)
    skill = await make_skill(session, "System design")
    role = await make_role(session, "Engineer", {skill: 3})
    from app.modules.skills.models import SkillLevel

    for _ in range(2):
        engineer = await make_user(job_role_id=role.id)
        session.add(SkillLevel(user_id=engineer.id, skill_id=skill.id, level=1))
    await session.commit()
    admin = await make_user("admin")
    home = (await client.get("/admin/home", headers=auth(admin))).json()
    metrics = {m["key"]: m for m in home["metrics"]}
    assert metrics["overdue"]["value"] == "1"
    assert metrics["on_time_compliance"]["value"] == "50%"
    assert any("not started" in a["text"] for a in home["attention"])
    assert home["content_gaps"][0] == {"skill_id": str(skill.id), "skill_name": "System design", "people": 2,
                                       "text": "System design: 2 people need it"}
