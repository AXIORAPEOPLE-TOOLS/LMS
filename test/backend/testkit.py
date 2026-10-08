"""Helpers and data builders shared by backend tests (importable as `testkit`)."""

from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.modules.assessments.models import SkillTest, TestQuestion
from app.modules.identity.models import User
from app.modules.learning.models import Course, CourseQuestion, Lesson
from app.modules.skills.models import JobRole, RoleSkill, Skill

UserFactory = Callable[..., Awaitable[User]]


def auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


async def make_skill(session: AsyncSession, name: str = "Customer communication", code: str | None = None) -> Skill:
    skill = Skill(code=code or name[:12].upper().replace(" ", "_"), name=name)
    session.add(skill)
    await session.commit()
    return skill


async def make_role(session: AsyncSession, name: str, requirements: dict[Skill, int]) -> JobRole:
    role = JobRole(code=name[:12].upper().replace(" ", "_"), name=name)
    session.add(role)
    await session.flush()
    for skill, level in requirements.items():
        session.add(RoleSkill(job_role_id=role.id, skill_id=skill.id, required_level=level))
    await session.commit()
    return role


async def make_course(
    session: AsyncSession,
    title: str = "Data privacy basics",
    *,
    lessons: int = 2,
    questions: int = 2,
    status: str = "published",
    simulation: bool = False,
    **fields: Any,
) -> Course:
    course = Course(title=title, status=status, **fields)
    session.add(course)
    await session.flush()
    for i in range(1, lessons + 1):
        session.add(Lesson(course_id=course.id, position=i, title=f"Lesson {i}", duration_minutes=5))
    if simulation:
        session.add(
            Lesson(
                course_id=course.id,
                position=lessons + 1,
                title="Practice",
                kind="simulation",
                scenario={
                    "steps": [{"id": "a", "label": "Sanitiser"}, {"id": "b", "label": "Gloves"}],
                    "correct_order": ["a", "b"],
                },
            )
        )
    for i in range(1, questions + 1):
        session.add(
            CourseQuestion(course_id=course.id, position=i, text=f"Q{i}?", options=["right", "wrong"], answer_index=0)
        )
    await session.commit()
    return course


async def make_test(session: AsyncSession, *, skill: Skill | None = None, questions: int = 4, **fields: Any) -> SkillTest:
    """Every question's right answer is option index 1."""
    test = SkillTest(skill_id=skill.id if skill else None, title=fields.pop("title", "Skill check"), **fields)
    session.add(test)
    await session.flush()
    for i in range(1, questions + 1):
        session.add(
            TestQuestion(test_id=test.id, position=i, text=f"Question {i}", options=["a", "b", "c", "d"], answer_index=1)
        )
    await session.commit()
    return test
