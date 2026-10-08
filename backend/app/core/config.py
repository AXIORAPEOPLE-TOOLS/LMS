"""Application configuration loaded from environment variables (12-factor).

Only infrastructure settings live here. Business defaults (thresholds, caps,
retention periods) live in the `app_settings` table so admins can change them
without a deploy (golden rule 8).
"""

import os
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env", env_file_encoding="utf-8", extra="ignore", env_prefix="LMS_"
    )

    environment: Literal["development", "test", "production"] = "development"
    app_name: str = "Learning & Knowledge Suite"
    timezone: str = "Asia/Kolkata"  # calendar days, due dates and quiet hours
    api_prefix: str = "/api"

    # Neon gives a URL like postgresql://user:pass@host/db?sslmode=require
    database_url: str = "sqlite+aiosqlite:///./lms-dev.db"
    database_echo: bool = False
    database_pool_size: int = 5

    jwt_secret: str = Field(default="change-me-in-production-please-32b", min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60 * 12

    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]

    # Background scheduler for reminders and timed workflows.
    scheduler_enabled: bool = False
    scheduler_interval_seconds: int = 300

    # Seed demo company on startup when the database is empty.
    seed_demo_data: bool = True

    # Serve the built frontend (single-binary / single-container mode).
    frontend_dist_dir: str | None = None

    # AI service provider: "rules" works offline; "groq" calls the Groq API.
    ai_provider: Literal["rules", "groq"] = "rules"
    groq_api_key: str | None = None
    groq_model: str = "openai/gpt-oss-120b"
    ai_timeout_seconds: float = 30.0

    # Redis (Upstash) and the BullMQ job queue between API and worker.
    redis_url: str | None = None
    queue_backend: Literal["inline", "bullmq"] = "inline"
    upstash_redis_rest_url: str | None = None
    upstash_redis_rest_token: str | None = None

    upload_dir: str = "uploads"
    max_upload_mb: int = 25

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [v.strip() for v in value.split(",") if v.strip()]
        return value

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    if os.environ.get("LMS_ENVIRONMENT") == "test":
        return Settings(_env_file=None)  # tests never read local secrets
    return Settings()
