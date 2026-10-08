from datetime import date, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import Response
from pydantic import Field

from app.core.deps import AdminUser, CurrentUser, SessionDep
from app.modules.certificates.service import CertificateService, status_of
from app.shared.schemas import Schema

router = APIRouter(tags=["certificates"])


class CertificateOut(Schema):
    id: UUID
    title: str
    code: str
    course_id: UUID | None
    test_id: UUID | None
    score: int | None
    issued_at: datetime
    valid_until: date | None
    status: str


class RevokeIn(Schema):
    reason: str = Field(min_length=3, max_length=300)


@router.get("/me/certificates", response_model=list[CertificateOut])
async def my_certificates(session: SessionDep, user: CurrentUser) -> list[CertificateOut]:
    return [
        CertificateOut.model_validate(c).model_copy(update={"status": status_of(c)})
        for c in await CertificateService(session).mine(user)
    ]


@router.get("/certificates/{certificate_id}/pdf")
async def certificate_pdf(certificate_id: UUID, request: Request, session: SessionDep, user: CurrentUser) -> Response:
    service = CertificateService(session)
    certificate = await service.get_owned(certificate_id, user)
    origin = request.headers.get("origin") or str(request.base_url)
    content = await service.pdf(certificate, origin)
    return Response(
        content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{certificate.code}.pdf"'},
    )


@router.get("/certificates/verify/{code}")
async def verify(code: str, session: SessionDep) -> dict[str, Any]:
    """Public: anyone with the ID or QR can check a certificate is real."""
    return await CertificateService(session).verify(code)


@router.post("/admin/certificates/{certificate_id}/revoke", status_code=204)
async def revoke(certificate_id: UUID, data: RevokeIn, session: SessionDep, admin: AdminUser) -> None:
    await CertificateService(session).revoke(certificate_id, data.reason, admin)
