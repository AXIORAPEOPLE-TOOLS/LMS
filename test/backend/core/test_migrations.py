"""Migrations must build exactly the schema the models describe (no drift)."""

from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine

from app.core.database import Base
from app.models_registry import load_all_models

BACKEND = Path(__file__).resolve().parents[3] / "backend"


def test_migrations_match_models(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    db = tmp_path / "migrated.db"
    monkeypatch.setenv("LMS_DATABASE_URL", f"sqlite+aiosqlite:///{db}")
    from app.core.config import get_settings

    get_settings.cache_clear()
    try:
        config = Config(str(BACKEND / "alembic.ini"))
        config.set_main_option("script_location", str(BACKEND / "migrations"))
        command.upgrade(config, "head")
    finally:
        monkeypatch.delenv("LMS_DATABASE_URL")
        get_settings.cache_clear()
    load_all_models()
    engine = create_engine(f"sqlite:///{db}")
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    engine.dispose()
    assert diff == [], f"Models changed without a migration: run 'alembic revision --autogenerate'.\n{diff}"
