"""Database engine, session factory and declarative base."""

import uuid
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


# asyncpg does not understand libpq query options that Neon puts in its URLs.
_LIBPQ_ONLY_PARAMS = {"sslmode", "channel_binding", "options"}


def normalize_database_url(raw_url: str) -> tuple[str, dict[str, Any]]:
    """Turn a Neon/libpq style URL into an asyncpg URL plus connect args."""
    url = raw_url.strip()
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url[len("postgresql://") :]
    if not url.startswith("postgresql+asyncpg://"):
        return url, {}

    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query))
    connect_args: dict[str, Any] = {}
    sslmode = query.get("sslmode")
    if sslmode and sslmode != "disable":
        connect_args["ssl"] = "require"
    if "-pooler" in (parts.hostname or ""):
        # Neon's PgBouncer supports protocol-level prepared statements, but names
        # must be unique across client connections. Keep asyncpg's cache (one round
        # trip per query instead of two) and give every statement a unique name.
        connect_args["prepared_statement_name_func"] = lambda: f"__asyncpg_{uuid.uuid4()}__"
    kept = {k: v for k, v in query.items() if k not in _LIBPQ_ONLY_PARAMS}
    clean = urlunsplit(parts._replace(query=urlencode(kept)))
    return clean, connect_args


def build_engine(database_url: str | None = None) -> AsyncEngine:
    settings = get_settings()
    url, connect_args = normalize_database_url(database_url or settings.database_url)
    kwargs: dict[str, Any] = {"echo": settings.database_echo, "connect_args": connect_args}
    if url.startswith("postgresql"):
        kwargs |= {
            "pool_size": settings.database_pool_size,
            "pool_pre_ping": True,  # Neon closes idle connections.
            "pool_recycle": 300,
        }
    engine = create_async_engine(url, **kwargs)
    if url.startswith("sqlite"):
        _enable_sqlite_foreign_keys(engine)
    return engine


def _enable_sqlite_foreign_keys(engine: AsyncEngine) -> None:
    from sqlalchemy import event

    @event.listens_for(engine.sync_engine, "connect")
    def _on_connect(dbapi_connection: Any, _: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


class Database:
    """Holds the engine and session factory; replaceable in tests."""

    def __init__(self, database_url: str | None = None) -> None:
        self.engine = build_engine(database_url)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False, autoflush=False)

    async def create_all(self) -> None:
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def dispose(self) -> None:
        await self.engine.dispose()


_database: Database | None = None


def get_database() -> Database:
    global _database
    if _database is None:
        _database = Database()
    return _database


def set_database(database: Database) -> None:
    global _database
    _database = database


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request, committed on success."""
    async with get_database().session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            session.info.pop("pending_jobs", None)
            raise
    # Only committed work reaches the queue (see app.core.queue).
    from app.core.queue import dispatch_pending

    await dispatch_pending(session)
