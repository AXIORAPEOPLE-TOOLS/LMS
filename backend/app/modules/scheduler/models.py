from datetime import datetime

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.models import UTCDateTime


class TaskRun(Base):
    """Last run of each scheduled task, so daily/weekly work happens exactly once."""

    __tablename__ = "task_runs"

    name: Mapped[str] = mapped_column(String(80), primary_key=True)
    last_run_at: Mapped[datetime] = mapped_column(UTCDateTime)
    last_result: Mapped[str] = mapped_column(Text, default="")
