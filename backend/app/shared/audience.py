"""Resolve 'who' for bulk actions: people, a job role, a department or everyone.

Shared by assignments, invitations, skill test campaigns and workflows so the
same audience picker works everywhere (golden rule: same pattern everywhere).
"""

from uuid import UUID

from pydantic import model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ValidationFailedError
from app.modules.identity.models import Department, User
from app.modules.skills.models import JobRole
from app.shared.schemas import Schema


class Audience(Schema):
    user_ids: list[UUID] = []
    job_role_id: UUID | None = None
    department_id: UUID | None = None
    everyone: bool = False

    @model_validator(mode="after")
    def _one_choice(self) -> "Audience":
        if not (self.user_ids or self.job_role_id or self.department_id or self.everyone):
            raise ValueError("Choose who this is for.")
        return self


class ResolvedAudience(Schema):
    label: str
    user_ids: list[UUID]


async def resolve_audience(session: AsyncSession, audience: Audience) -> ResolvedAudience:
    stmt = select(User).where(User.is_active.is_(True))
    label_parts: list[str] = []
    if audience.everyone:
        label_parts.append("Everyone")
    else:
        conditions = []
        if audience.user_ids:
            conditions.append(User.id.in_(audience.user_ids))
            label_parts.append(f"{len(audience.user_ids)} chosen people")
        if audience.job_role_id:
            role = await session.get(JobRole, audience.job_role_id)
            if role is None:
                raise ValidationFailedError("That role does not exist.")
            conditions.append(User.job_role_id == audience.job_role_id)
            label_parts.append(f"Role: {role.name}")
        if audience.department_id:
            dept = await session.get(Department, audience.department_id)
            if dept is None:
                raise ValidationFailedError("That department does not exist.")
            conditions.append(User.department_id == audience.department_id)
            label_parts.append(f"Department: {dept.name}")
        from sqlalchemy import or_

        stmt = stmt.where(or_(*conditions))
    users = (await session.scalars(stmt.order_by(User.full_name))).all()
    label = " + ".join(label_parts)
    return ResolvedAudience(label=f"{label} ({len(users)} people)", user_ids=[u.id for u in users])
