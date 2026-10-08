from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.certificates.service import CertificateService
from app.shared.events import DomainEvent, event_bus


async def issue_on_pass(session: AsyncSession, event: DomainEvent) -> None:
    payload = event.payload
    await CertificateService(session).issue(
        payload["user_id"],
        course_id=payload.get("course_id"),
        test_id=payload.get("test_id"),
        score=payload.get("score"),
    )


event_bus.subscribe("certification.passed", issue_on_pass)
