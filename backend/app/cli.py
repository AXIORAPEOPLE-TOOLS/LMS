"""Operations CLI.

uv run python -m app.cli migrate     # apply database migrations (Alembic)
uv run python -m app.cli seed        # load the demo company if the database is empty
uv run python -m app.cli run-tasks   # run due scheduled tasks once (for an external cron)
"""

import asyncio
import sys
from pathlib import Path


def migrate() -> None:
    """Upgrade to the latest schema. A database built earlier by create_all (no version table) is adopted."""
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, inspect

    from app.core.config import get_settings

    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    url = get_settings().database_url
    sync_url = url.replace("postgres://", "postgresql://").replace("+asyncpg", "").replace("+aiosqlite", "")
    if sync_url.startswith("postgresql://"):
        sync_url = sync_url.replace("postgresql://", "postgresql+psycopg://", 1).replace("&channel_binding=require", "")
    try:
        engine = create_engine(sync_url)
        tables = set(inspect(engine).get_table_names())
        engine.dispose()
    except Exception:
        tables = set()
    if tables and "alembic_version" not in tables and "users" in tables:
        print("Existing schema without migration history: marking it as current.")
        command.stamp(config, "head")
    command.upgrade(config, "head")


async def seed() -> None:
    from app.core.database import get_database
    from app.main import wire_modules
    from app.seed.demo import seed_if_empty

    wire_modules()
    async with get_database().session_factory() as session:
        created = await seed_if_empty(session)
        await session.commit()
    print("Demo company loaded." if created else "Database already has people; nothing seeded.")
    await get_database().dispose()


async def run_tasks() -> None:
    from app.core.database import get_database
    from app.main import wire_modules
    from app.modules.scheduler.registry import run_due_tasks

    wire_modules()
    print(await run_due_tasks(get_database().session_factory))
    await get_database().dispose()


def main() -> None:
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "migrate":
        migrate()
    elif command == "seed":
        asyncio.run(seed())
    elif command == "run-tasks":
        asyncio.run(run_tasks())
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
