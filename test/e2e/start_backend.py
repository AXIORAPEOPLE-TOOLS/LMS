"""Start a throwaway backend for end-to-end tests: fresh SQLite, demo company, no external services."""

import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[1] / "backend"
ARTIFACTS = HERE.parent / ".artifacts"
ARTIFACTS.mkdir(exist_ok=True)
DB = ARTIFACTS / "e2e.db"
for suffix in ("", "-journal", "-wal", "-shm"):
    Path(f"{DB}{suffix}").unlink(missing_ok=True)

env = {
    **os.environ,
    "LMS_ENVIRONMENT": "development",  # auto-create tables
    "LMS_DATABASE_URL": f"sqlite+aiosqlite:///{DB.as_posix()}",
    "LMS_SEED_DEMO_DATA": "true",
    "LMS_QUEUE_BACKEND": "inline",
    "LMS_AI_PROVIDER": "rules",
    "LMS_REDIS_URL": "",
    "LMS_SCHEDULER_ENABLED": "false",
    "LMS_UPLOAD_DIR": str(ARTIFACTS / "uploads"),
    "LMS_CORS_ORIGINS": "http://localhost:5174",
}
port = sys.argv[1] if len(sys.argv) > 1 else "8001"
sys.exit(subprocess.call(
    ["uv", "run", "--project", str(BACKEND), "uvicorn", "app.main:app", "--port", port, "--app-dir", str(BACKEND)],
    env=env, cwd=str(BACKEND),
))
