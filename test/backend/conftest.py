"""Shared fixtures for backend tests.

By default every test gets a fresh SQLite database (fast, no network).
Set TEST_DATABASE_URL to a throwaway PostgreSQL (e.g. a Neon branch) to run
the same tests against Postgres. Never point it at production data.
"""

import os
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

os.environ.setdefault("LMS_ENVIRONMENT", "test")
os.environ["LMS_SEED_DEMO_DATA"] = "false"
os.environ["LMS_SCHEDULER_ENABLED"] = "false"
os.environ["LMS_QUEUE_BACKEND"] = "inline"
os.environ["LMS_AI_PROVIDER"] = "rules"
# Uploads (knowledge files, proctoring pictures) go to a throwaway folder, never the repo.
os.environ["LMS_UPLOAD_DIR"] = tempfile.mkdtemp(prefix="lms-test-uploads-")

from app.core.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.core.database import Base, Database, set_database  # noqa: E402
from app.core.queue import InlineQueue, set_queue  # noqa: E402
from app.core.resilience import reset_breakers  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.main import create_app  # noqa: E402
from app.modules.ai.rules_provider import RulesProvider  # noqa: E402
from app.modules.ai.service import set_assistant  # noqa: E402
from app.modules.identity.models import User  # noqa: E402
from app.modules.monitoring.collector import metrics  # noqa: E402
from app.shared import clock  # noqa: E402
from testkit import UserFactory  # noqa: E402


@pytest.fixture
async def database(tmp_path: Path) -> AsyncIterator[Database]:
    url = os.environ.get("TEST_DATABASE_URL") or f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    db = Database(url)
    async with db.engine.begin() as conn:
        if url.startswith("postgres"):
            await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    set_database(db)
    yield db
    await db.dispose()


@pytest.fixture
def queue() -> InlineQueue:
    q = InlineQueue()
    set_queue(q)
    return q


@pytest.fixture(autouse=True)
def _deterministic_services() -> Any:
    set_assistant(RulesProvider())
    reset_breakers()
    metrics.__init__()  # fresh request metrics per test
    yield
    set_assistant(None)
    reset_breakers()
    clock.freeze(None)


@pytest.fixture
async def session(database: Database) -> AsyncIterator[AsyncSession]:
    async with database.session_factory() as s:
        yield s
        await s.commit()


@pytest.fixture
def app(database: Database, queue: InlineQueue) -> Any:
    return create_app()


@pytest.fixture
async def client(app: Any) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test/api") as c:
        yield c


DEFAULT_PASSWORD = "Passw0rd!"
_DEFAULT_HASH = hash_password(DEFAULT_PASSWORD)  # Argon2 is slow on purpose: hash once


@pytest.fixture
def make_user(database: Database) -> UserFactory:
    counter = {"n": 0}

    async def _make(
        *roles: str, full_name: str | None = None, password: str = DEFAULT_PASSWORD, **fields: Any
    ) -> User:
        counter["n"] += 1
        n = counter["n"]
        async with database.session_factory() as s:
            user = User(
                email=fields.pop("email", f"user{n}@example.com"),
                full_name=full_name or f"Test Person{n}",
                password_hash=_DEFAULT_HASH if password == DEFAULT_PASSWORD else hash_password(password),
                system_roles=["learner", *roles],
                **fields,
            )
            s.add(user)
            await s.commit()
            return user

    return _make
