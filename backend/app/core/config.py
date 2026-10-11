"""Application configuration loaded from environment variables (12-factor).

Only infrastructure settings live here. Business defaults (thresholds, caps,
retention periods) live in the `app_settings` table so admins can change them
without a deploy (golden rule 8).
"""

import os
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env", env_file_encoding="utf-8", extra="ignore", env_prefix="LMS_"
    )

    environment: Literal["development", "test", "production"] = "development"
    # One switch for the whole setup (docs/deployment.md). Each part below can still be set on its own.
    #   development: inline jobs, local files            (your machine, as today)
    #   single:      BullMQ on Redis, local files         (one server: API + worker side by side)
    #   scalable:    SQS + dead-letter queues, S3 files   (ECS on EC2, autoscaling)
    deploy_profile: Literal["development", "single", "scalable"] = "development"
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
    # Used to build full links in emails and WhatsApp messages.
    public_app_url: str = "http://localhost:5173"

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
    queue_backend: Literal["inline", "bullmq", "sqs"] | None = None  # None = from deploy_profile
    upstash_redis_rest_url: str | None = None
    upstash_redis_rest_token: str | None = None
    # Load and retries (infrastructure tuning, not business rules).
    worker_concurrency: int = 8  # jobs per queue per worker process; run more workers to scale out
    job_attempts: int = 5  # BullMQ retries a crashed job this many times
    job_backoff_ms: int = 5_000  # first retry after 5 s, then 10, 20, 40 s ...
    enqueue_batch_size: int = 200  # jobs per Redis round trip when many are sent at once
    inline_fallback_limit: int = 50  # Redis down: run at most this many jobs inline; the rest wait for the sweep
    notification_rate_per_second: int = 50  # cap on deliveries per second across all workers (provider limits)
    delivery_retry_attempts: int = 4  # a failed email/WhatsApp is retried this many times
    # API call log: one line per request (method, path, status, time). Slow calls are logged as warnings.
    log_requests: bool = True
    slow_request_ms: int = 1_000

    # Amazon SQS (scalable profile). An endpoint URL points at a local stand-in such as ElasticMQ.
    aws_region: str = "ap-southeast-1"
    sqs_endpoint_url: str | None = None
    sqs_queue_prefix: str = "lms-"  # lms-notifications, lms-authoring, ... (+ "-dlq")
    sqs_create_queues: bool = True  # create missing queues at start (dev/ElasticMQ); infra creates them in AWS
    sqs_visibility_seconds: int = 300  # a job is hidden this long while it runs (extended for long jobs)
    sqs_wait_seconds: int = 20  # long polling
    # The 5-minute scheduler: "worker" = timer in the worker (Redis lock with several workers);
    # "external" = EventBridge sends scheduler.run to the scheduled queue (scalable).
    scheduler_source: Literal["worker", "external"] = "worker"

    # Files (knowledge attachments, proctoring pictures): local folder or S3.
    storage_backend: Literal["local", "s3"] | None = None  # None = from deploy_profile
    upload_dir: str = "uploads"
    s3_bucket: str | None = None
    s3_prefix: str = ""
    s3_endpoint_url: str | None = None  # MinIO / LocalStack locally
    max_upload_mb: int = 25

    @field_validator("queue_backend", "storage_backend", mode="before")
    @classmethod
    def _empty_means_profile(cls, value: object) -> object:
        # LMS_QUEUE_BACKEND= (empty, as in .env.example) means "follow LMS_DEPLOY_PROFILE".
        return None if isinstance(value, str) and not value.strip() else value

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [v.strip() for v in value.split(",") if v.strip()]
        return value

    @model_validator(mode="after")
    def _apply_profile(self) -> "Settings":
        queue = {"development": "inline", "single": "bullmq", "scalable": "sqs"}[self.deploy_profile]
        storage = "s3" if self.deploy_profile == "scalable" else "local"
        if self.queue_backend is None:
            self.queue_backend = queue  # type: ignore[assignment]
        if self.storage_backend is None:
            self.storage_backend = storage  # type: ignore[assignment]
        problems = self.profile_problems()
        if problems:
            raise ValueError(f"LMS_DEPLOY_PROFILE={self.deploy_profile} is missing: " + "; ".join(problems))
        return self

    def profile_problems(self) -> list[str]:
        """What a profile needs, in plain words, so a deploy fails at start instead of half-working."""
        problems = []
        if self.queue_backend == "bullmq" and not self.redis_url:
            problems.append("LMS_REDIS_URL (BullMQ needs Redis)")
        if self.storage_backend == "s3" and not self.s3_bucket:
            problems.append("LMS_S3_BUCKET (files are stored in S3)")
        if self.deploy_profile == "scalable" and self.queue_backend != "sqs":
            problems.append("LMS_QUEUE_BACKEND=sqs (scalable uses SQS)")
        if self.deploy_profile == "scalable" and self.storage_backend != "s3":
            problems.append("LMS_STORAGE_BACKEND=s3 (several containers cannot share a local folder)")
        return problems

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    if os.environ.get("LMS_ENVIRONMENT") == "test":
        return Settings(_env_file=None)  # tests never read local secrets
    return Settings()
