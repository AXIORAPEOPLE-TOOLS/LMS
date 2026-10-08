"""Single source of 'now' so tests can freeze time.

Timestamps are stored in UTC. Calendar days (due dates, "today", quiet hours)
follow the organisation's timezone (LMS_TIMEZONE, default Asia/Kolkata).
"""

from datetime import UTC, date, datetime
from functools import lru_cache
from zoneinfo import ZoneInfo

_frozen: datetime | None = None


@lru_cache
def org_timezone() -> ZoneInfo:
    from app.core.config import get_settings

    return ZoneInfo(get_settings().timezone)


def utcnow() -> datetime:
    return _frozen or datetime.now(UTC)


def local_now() -> datetime:
    return utcnow().astimezone(org_timezone())


def today() -> date:
    """The current calendar day where the organisation works."""
    return local_now().date()


def freeze(at: datetime | None) -> None:
    """Freeze the clock (tests only). Pass None to unfreeze."""
    global _frozen
    _frozen = at
