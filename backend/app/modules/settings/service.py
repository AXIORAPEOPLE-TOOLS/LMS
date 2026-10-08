from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.modules.settings.defaults import DEFAULTS
from app.modules.settings.models import AppSetting


class SettingsService:
    """Reads a setting from the database, falling back to the spec default."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self._cache: dict[str, Any] | None = None

    async def _load(self) -> dict[str, Any]:
        if self._cache is None:
            rows = (await self.session.scalars(select(AppSetting))).all()
            self._cache = {row.key: row.value for row in rows}
        return self._cache

    async def get(self, key: str) -> Any:
        if key not in DEFAULTS:
            raise KeyError(f"Unknown setting {key}")
        overrides = await self._load()
        return overrides.get(key, DEFAULTS[key][0])

    async def all(self) -> list[dict[str, Any]]:
        overrides = await self._load()
        return [
            {
                "key": key,
                "value": overrides.get(key, default),
                "default": default,
                "description": description,
                "is_overridden": key in overrides,
            }
            for key, (default, description) in DEFAULTS.items()
        ]

    async def set(self, key: str, value: Any, actor_id: UUID | None) -> None:
        if key not in DEFAULTS:
            raise NotFoundError("That setting does not exist.")
        row = await self.session.get(AppSetting, key)
        if row is None:
            self.session.add(AppSetting(key=key, value=value, updated_by_id=actor_id))
        else:
            row.value = value
            row.updated_by_id = actor_id
        await self.session.flush()
        if self._cache is not None:
            self._cache[key] = value
