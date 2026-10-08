from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import func, select

from app.modules.identity.models import Department, User
from app.shared.repository import Repository


class UserRepository(Repository[User]):
    model = User
    not_found_message = "We could not find that person."

    async def by_email(self, email: str) -> User | None:
        return await self.first(func.lower(User.email) == email.lower())

    async def team_of(self, manager_id: UUID) -> Sequence[User]:
        return await self.list(User.manager_id == manager_id, User.is_active.is_(True), order_by=User.full_name)

    async def active(self) -> Sequence[User]:
        return await self.list(User.is_active.is_(True), order_by=User.full_name)

    async def with_job_role(self, job_role_id: UUID) -> Sequence[User]:
        return await self.list(User.job_role_id == job_role_id, User.is_active.is_(True))

    async def names_by_id(self, ids: set[UUID]) -> dict[UUID, str]:
        if not ids:
            return {}
        rows = await self.session.execute(select(User.id, User.full_name).where(User.id.in_(ids)))
        return {row[0]: row[1] for row in rows}


class DepartmentRepository(Repository[Department]):
    model = Department
    not_found_message = "We could not find that department."

    async def by_name(self, name: str) -> Department | None:
        return await self.first(func.lower(Department.name) == name.lower())

    async def all_by_id(self) -> dict[UUID, Department]:
        return {d.id: d for d in await self.list(order_by=Department.name)}
