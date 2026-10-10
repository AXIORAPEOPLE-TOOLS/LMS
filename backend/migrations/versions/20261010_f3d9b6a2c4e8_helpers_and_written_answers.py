"""helpers (agent runs) and written answers

Revision ID: f3d9b6a2c4e8
Revises: e7c1a9d3b5f2
Create Date: 2026-10-10 22:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import app.shared.models

revision: str = "f3d9b6a2c4e8"
down_revision: str | Sequence[str] | None = "e7c1a9d3b5f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("courses", sa.Column("quiz_time_limit_minutes", sa.Integer(), nullable=True))
    op.add_column("course_questions", sa.Column("kind", sa.String(length=12), server_default="choice", nullable=False))
    op.add_column("course_questions", sa.Column("model_answer", sa.Text(), server_default="", nullable=False))
    op.add_column("course_questions", sa.Column("rubric", sa.JSON(), server_default=sa.text("'[]'"), nullable=False))
    op.add_column("course_quiz_attempts", sa.Column("written", sa.JSON(), server_default=sa.text("'{}'"), nullable=False))
    op.add_column(
        "course_quiz_attempts", sa.Column("review_status", sa.String(length=12), server_default="none", nullable=False)
    )
    op.add_column("course_quiz_attempts", sa.Column("reviewer_id", sa.Uuid(), nullable=True))
    op.add_column(
        "course_quiz_attempts", sa.Column("reviewed_at", app.shared.models.UTCDateTime(timezone=True), nullable=True)
    )
    op.create_index(op.f("ix_course_quiz_attempts_review_status"), "course_quiz_attempts", ["review_status"])

    op.create_table(
        "agent_runs",
        sa.Column("kind", sa.String(length=12), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("brief", sa.JSON(), nullable=False),
        sa.Column("steps", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("course_id", sa.Uuid(), nullable=True),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("engine", sa.String(length=12), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("finished_at", app.shared.models.UTCDateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", app.shared.models.UTCDateTime(timezone=True), nullable=False),
        sa.Column("updated_at", app.shared.models.UTCDateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("kind", "status", "course_id", "created_by_id"):
        op.create_index(op.f(f"ix_agent_runs_{column}"), "agent_runs", [column])


def downgrade() -> None:
    op.drop_table("agent_runs")
    op.drop_index(op.f("ix_course_quiz_attempts_review_status"), table_name="course_quiz_attempts")
    for column in ("reviewed_at", "reviewer_id", "review_status", "written"):
        op.drop_column("course_quiz_attempts", column)
    for column in ("rubric", "model_answer", "kind"):
        op.drop_column("course_questions", column)
    op.drop_column("courses", "quiz_time_limit_minutes")
