from datetime import UTC, date, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Database
from app.modules.certificates.models import Certificate
from app.modules.certificates.service import CertificateService, add_months
from app.modules.notifications.models import Notification
from app.shared import clock
from testkit import UserFactory, auth, make_course


def test_validity_matches_deck_example() -> None:
    assert add_months(date(2026, 10, 12), 12) == date(2027, 10, 11)
    assert add_months(date(2024, 1, 31), 1) == date(2024, 2, 28)


async def test_certification_course_issues_certificate_and_renewal_keeps_history(
    client: AsyncClient, session: AsyncSession, make_user: UserFactory, database: Database
) -> None:
    course = await make_course(session, "Fire safety", lessons=1, questions=0, kind="certification", validity_months=12)
    learner = await make_user()
    lesson = (await client.get(f"/courses/{course.id}", headers=auth(learner))).json()["lessons"][0]
    done = (await client.post(f"/lessons/{lesson['id']}/complete", headers=auth(learner))).json()
    assert done["course_completed"] is True
    certs = (await client.get("/me/certificates", headers=auth(learner))).json()
    assert [c["title"] for c in certs] == ["Fire safety"]

    async with database.session_factory() as s:
        await CertificateService(s).issue(learner.id, course_id=course.id)
        await s.commit()
    certs = (await client.get("/me/certificates", headers=auth(learner))).json()
    assert len(certs) == 1  # the old one is kept as history, not shown twice
    total = (await session.scalars(select(Certificate).where(Certificate.user_id == learner.id))).all()
    assert len(total) == 2


async def test_renewal_reminders_at_60_30_and_7_days(database: Database, make_user: UserFactory, session: AsyncSession) -> None:
    learner = await make_user()
    async with database.session_factory() as s:
        cert = await CertificateService(s).issue(learner.id)
        cert.valid_until = date(2026, 12, 31)
        await s.commit()

    sent = []
    for day in (date(2026, 10, 1), date(2026, 11, 1), date(2026, 11, 2), date(2026, 12, 1), date(2026, 12, 24)):
        clock.freeze(datetime(day.year, day.month, day.day, 10, tzinfo=UTC))
        async with database.session_factory() as s:
            sent.append(await CertificateService(s).send_renewal_reminders())
            await s.commit()
    assert sent == [0, 1, 0, 1, 1]  # 60 days, 30 days, 7 days; never twice
    reminders = (await session.scalars(select(Notification).where(Notification.kind == "reminder"))).all()
    assert len(reminders) == 3


async def test_verify_unknown_code(client: AsyncClient) -> None:
    response = await client.get("/certificates/verify/C-2026-999999")
    assert response.status_code == 404


async def test_revoked_certificate_shows_as_revoked(
    client: AsyncClient, database: Database, make_user: UserFactory
) -> None:
    learner = await make_user()
    admin = await make_user("admin")
    async with database.session_factory() as s:
        cert = await CertificateService(s).issue(learner.id)
        await s.commit()
    await client.post(f"/admin/certificates/{cert.id}/revoke", json={"reason": "Issued in error"}, headers=auth(admin))
    assert (await client.get(f"/certificates/verify/{cert.code}")).json()["status"] == "revoked"
    clock.freeze(datetime.now(UTC) + timedelta(days=1))
