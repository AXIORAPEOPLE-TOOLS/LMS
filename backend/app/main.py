"""Application factory. `uvicorn app.main:app` or `fastapi run app/main.py`."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib import import_module
from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import get_settings
from app.core.database import get_database
from app.core.errors import register_error_handlers
from app.core.health import router as health_router
from app.core.logging import configure_logging
from app.core.middleware import register_middleware
from app.models_registry import load_all_models

logger = logging.getLogger(__name__)

# Each feature module exposes `router`. Order only affects the OpenAPI listing.
ROUTER_MODULES = [
    "app.modules.identity.router",
    "app.modules.skills.router",
    "app.modules.settings.router",
    "app.modules.audit.router",
    "app.modules.notifications.router",
    "app.modules.learning.router",
    "app.modules.assessments.router",
    "app.modules.certificates.router",
    "app.modules.pathways.router",
    "app.modules.gamification.router",
    "app.modules.career.router",
    "app.modules.home.router",
    "app.modules.manager.router",
    "app.modules.reminders.router",
    "app.modules.scheduler.router",
    "app.modules.workflows.router",
    "app.modules.admin_home.router",
    "app.modules.reports.router",
    "app.modules.knowledge.router",
    "app.modules.monitoring.router",
]

# Modules that subscribe to domain events at startup.
SUBSCRIBER_MODULES = [
    "app.modules.certificates.subscribers",
    "app.modules.pathways.subscribers",
    "app.modules.gamification.subscribers",
    "app.modules.workflows.subscribers",
]

JOB_MODULES = [
    "app.modules.notifications.jobs",
    "app.modules.learning.jobs",
    "app.modules.scheduler.jobs",
    "app.modules.knowledge.jobs",
]


def wire_modules() -> None:
    """Load models, event subscribers and job handlers (idempotent)."""
    load_all_models()
    for module in (*SUBSCRIBER_MODULES, *JOB_MODULES):
        import_module(module)


def build_api_router() -> APIRouter:
    api = APIRouter()
    for module in ROUTER_MODULES:
        api.include_router(import_module(module).router)
    return api


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    database = get_database()
    if settings.environment != "production":
        if database.engine.dialect.name == "sqlite":
            await database.create_all()  # throwaway test/e2e databases
        else:
            # Same path as production: Alembic migrations (never create_all on Postgres).
            import asyncio

            from app.cli import migrate

            await asyncio.to_thread(migrate)
    if settings.seed_demo_data:
        from app.seed.demo import seed_if_empty

        async with database.session_factory() as session:
            await seed_if_empty(session)
            await session.commit()
    scheduler = None
    if settings.scheduler_enabled:
        from app.modules.scheduler.runner import Scheduler

        scheduler = Scheduler(settings.scheduler_interval_seconds)
        scheduler.start()
    yield
    if scheduler:
        await scheduler.stop()
    from app.core.queue import get_queue

    await get_queue().close()
    await database.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.environment)
    wire_modules()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
        docs_url=f"{settings.api_prefix}/docs",
        openapi_url=f"{settings.api_prefix}/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    register_error_handlers(app)
    register_middleware(app)

    app.include_router(health_router, prefix=settings.api_prefix)
    app.include_router(build_api_router(), prefix=settings.api_prefix)
    if settings.frontend_dist_dir:
        _mount_frontend(app, Path(settings.frontend_dist_dir))
    return app


def _mount_frontend(app: FastAPI, dist: Path) -> None:
    """Serve the built React app from the same process (single container / exe)."""
    if not (dist / "index.html").exists():
        logger.warning("Frontend build not found at %s", dist)
        return
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str) -> FileResponse:
        candidate = (dist / path).resolve()
        if path and candidate.is_file() and dist.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(dist / "index.html")


app = create_app()
