"""course quiz attempts

Revision ID: d4b8e2f7a610
Revises: c2a7d4e91f03
Create Date: 2026-10-10 17:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import app.shared.models

revision: str = "d4b8e2f7a610"
down_revision: str | Sequence[str] | None = "c2a7d4e91f03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "course_quiz_attempts",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("course_id", sa.Uuid(), nullable=False),
        sa.Column("assignment_id", sa.Uuid(), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("answers", sa.JSON(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("submitted_at", app.shared.models.UTCDateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["assignment_id"], ["assignments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_course_quiz_attempts_assignment_id"), "course_quiz_attempts", ["assignment_id"])
    op.create_index(op.f("ix_course_quiz_attempts_course_id"), "course_quiz_attempts", ["course_id"])
    op.create_index(op.f("ix_course_quiz_attempts_user_id"), "course_quiz_attempts", ["user_id"])


def downgrade() -> None:
    op.drop_table("course_quiz_attempts")
