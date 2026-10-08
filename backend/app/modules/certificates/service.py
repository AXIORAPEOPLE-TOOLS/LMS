"""Certificates (L-06): issue on pass, verify by code or QR, PDF, renewal reminders."""

import io
from collections.abc import Sequence
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.modules.assessments.models import SkillTest
from app.modules.audit.service import AuditService
from app.modules.certificates.models import Certificate
from app.modules.identity.models import User
from app.modules.learning.models import Course
from app.modules.notifications.models import NotificationKind
from app.modules.notifications.service import NotificationService
from app.modules.settings.service import SettingsService
from app.shared.clock import today, utcnow
from app.shared.events import DomainEvent, event_bus


def add_months(start: date, months: int) -> date:
    """12 Oct 2026 + 12 months -> 11 Oct 2027 (valid *until* the day before)."""
    from datetime import timedelta

    month = start.month - 1 + months
    year = start.year + month // 12
    month = month % 12 + 1
    day = min(
        start.day,
        [31, 29 if year % 4 == 0 and (year % 100 or year % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1],
    )
    return date(year, month, day) - timedelta(days=1)


class CertificateService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def issue(
        self, user_id: UUID, *, course_id: UUID | None = None, test_id: UUID | None = None, score: int | None = None
    ) -> Certificate:
        title, months = await self._subject(course_id, test_id)
        if months is None:
            months = await SettingsService(self.session).get("certificates.validity_months")
        # Older certificates for the same subject are kept as history ("renewed").
        previous = (
            await self.session.scalars(
                select(Certificate).where(
                    Certificate.user_id == user_id,
                    Certificate.status == "valid",
                    (Certificate.course_id == course_id) if course_id else (Certificate.test_id == test_id),
                )
            )
        ).all()
        for old in previous:
            old.status = "renewed"
        certificate = Certificate(
            user_id=user_id,
            title=title,
            code=await self._next_code(),
            course_id=course_id,
            test_id=test_id,
            score=score,
            valid_until=add_months(today(), months) if months else None,
        )
        self.session.add(certificate)
        await self.session.flush()
        await NotificationService(self.session).notify(
            user_id,
            kind=NotificationKind.SYSTEM,
            title=f"Your certificate is ready: {title}",
            link="/learn/certificates",
            related=("certificate", certificate.id),
        )
        await event_bus.publish(
            self.session, DomainEvent("certificate.issued", {"user_id": user_id, "certificate_id": certificate.id})
        )
        return certificate

    async def _subject(self, course_id: UUID | None, test_id: UUID | None) -> tuple[str, int | None]:
        if test_id:
            test = await self.session.get(SkillTest, test_id)
            if test:
                return test.certificate_title or test.title.removesuffix(" test"), test.validity_months
        if course_id:
            course = await self.session.get(Course, course_id)
            if course:
                return course.title, course.validity_months
        return "Certificate of completion", None

    async def _next_code(self) -> str:
        year = utcnow().year
        count = int(await self.session.scalar(select(func.count()).where(Certificate.code.like(f"C-{year}-%"))) or 0)
        return f"C-{year}-{count + 1:06d}"

    async def mine(self, user: User) -> Sequence[Certificate]:
        return (
            await self.session.scalars(
                select(Certificate)
                .where(Certificate.user_id == user.id, Certificate.status != "renewed")
                .order_by(Certificate.issued_at.desc())
            )
        ).all()

    async def get_owned(self, certificate_id: UUID, user: User) -> Certificate:
        certificate = await self.session.get(Certificate, certificate_id)
        if certificate is None or (certificate.user_id != user.id and not user.has_role("admin")):
            raise NotFoundError("We could not find that certificate.")
        return certificate

    async def verify(self, code: str) -> dict[str, Any]:
        certificate = (await self.session.scalars(select(Certificate).where(Certificate.code == code.upper()))).first()
        if certificate is None:
            raise NotFoundError("No certificate has this ID.")
        holder = await self.session.get(User, certificate.user_id)
        return {
            "code": certificate.code,
            "holder": holder.full_name if holder else "Former employee",
            "title": certificate.title,
            "issued_on": certificate.issued_at.date().isoformat(),
            "valid_until": certificate.valid_until.isoformat() if certificate.valid_until else None,
            "status": status_of(certificate),
        }

    async def revoke(self, certificate_id: UUID, reason: str, actor: User) -> Certificate:
        certificate = await self.session.get(Certificate, certificate_id)
        if certificate is None:
            raise NotFoundError("We could not find that certificate.")
        if certificate.status == "revoked":
            raise ConflictError("This certificate is already revoked.")
        certificate.status = "revoked"
        certificate.revoked_reason = reason
        AuditService(self.session).record("certificate.revoked", "certificate", certificate.id, actor_id=actor.id, reason=reason)
        return certificate

    async def send_renewal_reminders(self) -> int:
        """60, 30 and 7 days before expiry (settings). Returns reminders sent."""
        days_list: list[int] = await SettingsService(self.session).get("certificates.renewal_reminder_days")
        horizon = max(days_list)
        from datetime import timedelta

        upcoming = (
            await self.session.scalars(
                select(Certificate).where(
                    Certificate.status == "valid",
                    Certificate.valid_until.is_not(None),
                    Certificate.valid_until <= today() + timedelta(days=horizon),
                    Certificate.valid_until >= today(),
                )
            )
        ).all()
        sent = 0
        notifications = NotificationService(self.session)
        for certificate in upcoming:
            assert certificate.valid_until is not None
            left = (certificate.valid_until - today()).days
            due = [d for d in days_list if left <= d and d not in (certificate.renewal_reminders_sent or [])]
            if not due:
                continue
            certificate.renewal_reminders_sent = [*(certificate.renewal_reminders_sent or []), *due]
            result = await notifications.notify(
                certificate.user_id,
                kind=NotificationKind.REMINDER,
                title=f"Your {certificate.title} certificate ends in {left} days",
                body="Renew it in a few minutes so it stays valid.",
                link="/learn/certificates",
                related=("certificate", certificate.id),
                automatic=True,
            )
            sent += 1 if result else 0
        return sent

    async def pdf(self, certificate: Certificate, verify_base_url: str) -> bytes:
        import segno
        from fpdf import FPDF

        holder = await self.session.get(User, certificate.user_id)
        pdf = FPDF(orientation="L", unit="mm", format="A4")
        pdf.set_auto_page_break(False)
        pdf.add_page()
        green, gold = (31, 92, 78), (184, 134, 11)
        pdf.set_draw_color(*gold)
        pdf.set_line_width(1.2)
        pdf.rect(12, 12, 273, 186)
        pdf.set_text_color(*gold)
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_xy(0, 40)
        pdf.cell(297, 8, "C E R T I F I C A T E   O F   C O M P L E T I O N", align="C")
        pdf.set_text_color(*green)
        pdf.set_font("Times", "B", 40)
        pdf.set_xy(0, 62)
        pdf.cell(297, 18, _latin(holder.full_name if holder else ""), align="C")
        pdf.set_text_color(80, 90, 90)
        pdf.set_font("Helvetica", "", 16)
        pdf.set_xy(0, 92)
        valid = f" | valid until {certificate.valid_until:%d %b %Y}" if certificate.valid_until else ""
        pdf.cell(297, 10, _latin(f"{certificate.title} | {certificate.issued_at:%d %b %Y}{valid}"), align="C")
        qr = segno.make(f"{verify_base_url.rstrip('/')}/verify/{certificate.code}", error="m")
        buffer = io.BytesIO()
        qr.save(buffer, kind="png", scale=6, border=1)
        buffer.seek(0)
        pdf.image(buffer, x=40, y=125, w=45, h=45)
        pdf.set_text_color(30, 40, 40)
        pdf.set_font("Helvetica", "B", 13)
        pdf.set_xy(95, 135)
        pdf.cell(120, 8, "Scan to verify")
        pdf.set_font("Helvetica", "", 12)
        pdf.set_xy(95, 145)
        pdf.cell(120, 8, f"Certificate ID {certificate.code}")
        return bytes(pdf.output())


def status_of(certificate: Certificate) -> str:
    if certificate.status == "revoked":
        return "revoked"
    if certificate.valid_until and certificate.valid_until < today():
        return "expired"
    return "valid"


def _latin(text: str) -> str:
    return text.encode("latin-1", errors="replace").decode("latin-1")
