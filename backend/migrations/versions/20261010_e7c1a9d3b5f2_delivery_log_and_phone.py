"""delivery log and phone

Revision ID: e7c1a9d3b5f2
Revises: d4b8e2f7a610
Create Date: 2026-10-10 19:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import app.shared.models

revision: str = "e7c1a9d3b5f2"
down_revision: str | Sequence[str] | None = "d4b8e2f7a610"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("phone", sa.String(length=20), nullable=True))
    op.create_table(
        "delivery_logs",
        sa.Column("notification_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column("to_address", sa.String(length=255), nullable=True),
        sa.Column("subject", sa.String(length=200), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("reason", sa.String(length=200), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("is_automatic", sa.Boolean(), nullable=False),
        sa.Column("created_at", app.shared.models.UTCDateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["notification_id"], ["notifications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("notification_id", "user_id", "channel", "status", "created_at"):
        op.create_index(op.f(f"ix_delivery_logs_{column}"), "delivery_logs", [column])


def downgrade() -> None:
    op.drop_table("delivery_logs")
    op.drop_column("users", "phone")
