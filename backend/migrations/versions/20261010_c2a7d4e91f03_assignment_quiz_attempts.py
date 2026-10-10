"""assignment quiz attempts

Revision ID: c2a7d4e91f03
Revises: b151ab58b169
Create Date: 2026-10-10 15:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c2a7d4e91f03"
down_revision: str | Sequence[str] | None = "b151ab58b169"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("assignments", sa.Column("quiz_attempts", sa.Integer(), server_default="0", nullable=False))


def downgrade() -> None:
    op.drop_column("assignments", "quiz_attempts")
