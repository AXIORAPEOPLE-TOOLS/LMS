from datetime import UTC, date, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Database
from app.modules.gamification import rules
from app.modules.gamification.models import Badge, Challenge, PointEntry
from app.modules.gamification.service import GamificationService
from app.modules.identity.models import Department
from app.modules.learning.models import Assignment
from app.modules.settings.defaults import DEFAULTS
from app.modules.skills.models import SkillLevel
from app.shared import clock
from testkit import UserFactory, auth, make_course, make_skill


def test_profile_level_matches_deck() -> None:
    level = rules.profile_level(1240, DEFAULTS["gamification.levels"][0])
    assert (level.name, level.next_name, level.points_to_next) == ("Practitioner", "Specialist", 260)


def test_streak_counts_consecutive_days() -> None:
    today = date(2026, 10, 9)
    days = {today - timedelta(days=i) for i in range(5)} | {today - timedelta(days=9)}
    assert rules.streak_days(days, today) == 5
    assert rules.streak_days(days - {today}, today) == 4  # today not done yet: streak kept
    assert rules.streak_days(set(), today) == 0


async def test_points_only_once_and_badges(client: AsyncClient, session: AsyncSession, make_user: UserFactory) -> None:
    session.add(Badge(code="first_step", name="First Step", description="Finish your first lesson",
                      rule={"type": "count", "reason": "lesson", "at_least": 1}))
    await session.commit()
    course = await make_course(session, lessons=1, questions=0)
    learner = await make_user()
    lesson = (await client.get(f"/courses/{course.id}", headers=auth(learner))).json()["lessons"][0]
    await client.post(f"/lessons/{lesson['id']}/complete", headers=auth(learner))
    await client.post(f"/lessons/{lesson['id']}/complete", headers=auth(learner))  # repeat: no extra points

    profile = (await client.get("/me/profile", headers=auth(learner))).json()
    assert profile["points"] == 10 + 30  # lesson + course
    assert profile["week_lessons"] == 1 and profile["streak_days"] == 1
    badges = (await client.get("/me/badges", headers=auth(learner))).json()
    assert badges["earned"] == 1 and badges["badges"][0]["code"] == "first_step"


async def test_boards_hide_names_and_show_me(client: AsyncClient, session: AsyncSession, make_user: UserFactory) -> None:
    skill = await make_skill(session)
    me = await make_user(full_name="Asha Verma")
    riya = await make_user(full_name="Riya Sharma")
    shy = await make_user(full_name="Hidden Person", show_name_on_boards=False)
    for person, score in ((riya, 92), (shy, 81), (me, 74)):
        session.add(SkillLevel(user_id=person.id, skill_id=skill.id, level=4, score=score))
    await session.commit()
    board = (await client.get(f"/leaderboards/skill_champions?skill_id={skill.id}", headers=auth(me))).json()
    assert [r["name"] for r in board["rows"]] == ["Riya S.", "A colleague", "You (Asha V.)"]
    assert board["rows"][1]["user_id"] is None  # hidden people cannot be looked up
    assert board["rows"][2]["is_me"] is True and board["version"]


async def test_compliance_is_by_department_only(client: AsyncClient, session: AsyncSession, make_user: UserFactory) -> None:
    dept = Department(name="Support")
    session.add(dept)
    await session.commit()
    course = await make_course(session)
    a = await make_user(department_id=dept.id)
    b = await make_user(department_id=dept.id)
    past = clock.today() - timedelta(days=3)
    session.add_all([
        Assignment(user_id=a.id, course_id=course.id, is_mandatory=True, due_on=past, status="completed",
                   completed_at=datetime.now(UTC) - timedelta(days=5)),
        Assignment(user_id=b.id, course_id=course.id, is_mandatory=True, due_on=past, status="not_started"),
    ])
    await session.commit()
    body = (await client.get("/leaderboards/compliance", headers=auth(a))).json()
    assert body == {"rows": [{"department": "Support", "on_time_pct": 50, "assigned": 2}]}


async def test_challenge_join_and_win(
    client: AsyncClient, session: AsyncSession, make_user: UserFactory, database: Database
) -> None:
    course = await make_course(session, lessons=1, questions=0)
    learner = await make_user()
    challenge = Challenge(title="Team week", goal_pct=80, starts_on=clock.today(), ends_on=clock.today() + timedelta(days=3),
                          reward_points=50)
    session.add(challenge)
    session.add(Assignment(user_id=learner.id, course_id=course.id))
    await session.commit()
    joined = (await client.post(f"/challenges/{challenge.id}/join", headers=auth(learner))).json()
    assert joined["joined"] is True and joined["team_pct"] == 0 and joined["my_part"][0].startswith("Finish")

    lesson = (await client.get(f"/courses/{course.id}", headers=auth(learner))).json()["lessons"][0]
    await client.post(f"/lessons/{lesson['id']}/complete", headers=auth(learner))
    async with database.session_factory() as s:
        assert await GamificationService(s).settle_challenges() == 1
        await s.commit()
    points = (await session.scalars(select(PointEntry))).all()
    assert any(p.reason == "challenge" and p.points == 50 for p in points)
    clock.freeze(None)
