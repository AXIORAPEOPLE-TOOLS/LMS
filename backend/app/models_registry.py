"""Import every module's models so SQLAlchemy metadata (and Alembic) sees all tables."""

from importlib import import_module

MODEL_MODULES = [
    "app.modules.settings.models",
    "app.modules.audit.models",
    "app.modules.identity.models",
    "app.modules.skills.models",
    "app.modules.notifications.models",
    "app.modules.learning.models",
    "app.modules.assessments.models",
    "app.modules.certificates.models",
    "app.modules.pathways.models",
    "app.modules.gamification.models",
    "app.modules.scheduler.models",
    "app.modules.workflows.models",
    "app.modules.reports.models",
    "app.modules.knowledge.models",
    "app.modules.agents.models",
]


def load_all_models() -> None:
    for module in MODEL_MODULES:
        import_module(module)
