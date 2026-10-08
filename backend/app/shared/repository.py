"""Generic async repository: the only place that talks SQL for simple CRUD.

Module repositories subclass this and add their own query methods, so services
depend on an intention-revealing API instead of raw SQLAlchemy (DIP).
"""

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Base
from app.core.errors import NotFoundError


class Repository[ModelT: Base]:
    model: type[ModelT]
    not_found_message = "We could not find that item."

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, entity_id: UUID) -> ModelT | None:
        return await self.session.get(self.model, entity_id)

    async def get_or_raise(self, entity_id: UUID) -> ModelT:
        entity = await self.get(entity_id)
        if entity is None:
            raise NotFoundError(self.not_found_message)
        return entity

    async def list(self, *where: Any, order_by: Any = None, limit: int | None = None) -> Sequence[ModelT]:
        stmt = select(self.model).where(*where)
        if order_by is not None:
            stmt = stmt.order_by(*order_by) if isinstance(order_by, (list, tuple)) else stmt.order_by(order_by)
        if limit is not None:
            stmt = stmt.limit(limit)
        return (await self.session.scalars(stmt)).all()

    async def first(self, *where: Any) -> ModelT | None:
        return (await self.session.scalars(select(self.model).where(*where).limit(1))).first()

    async def count(self, *where: Any) -> int:
        stmt = select(func.count()).select_from(self.model).where(*where)
        return int((await self.session.scalar(stmt)) or 0)

    async def scalars(self, stmt: Select[Any]) -> Sequence[Any]:
        return (await self.session.scalars(stmt)).all()

    def add(self, entity: ModelT) -> ModelT:
        self.session.add(entity)
        return entity

    async def add_and_flush(self, entity: ModelT) -> ModelT:
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def delete(self, entity: ModelT) -> None:
        await self.session.delete(entity)
        await self.session.flush()
