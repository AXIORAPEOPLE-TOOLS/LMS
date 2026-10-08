"""When may we remind someone? Pure functions over local (organisation) time."""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta


def parse_hhmm(value: str) -> time:
    hours, minutes = value.split(":")
    return time(int(hours), int(minutes))


@dataclass(frozen=True)
class ReminderPolicy:
    quiet_start: time  # no messages before
    quiet_end: time  # no messages after
    allow_weekends: bool
    holidays: frozenset[date]
    max_per_day: int
    max_per_week: int

    def day_allowed(self, day: date) -> bool:
        if day in self.holidays:
            return False
        return self.allow_weekends or day.weekday() < 5


def next_send_time(now: datetime, window: tuple[time, time], policy: ReminderPolicy, *, horizon_days: int = 7) -> datetime | None:
    """Earliest moment >= now inside the person's window AND allowed hours, on an allowed day."""
    start = max(window[0], policy.quiet_start)
    end = min(window[1], policy.quiet_end)
    if start >= end:  # the window is outside allowed hours: fall back to allowed hours
        start, end = policy.quiet_start, policy.quiet_end
    for offset in range(horizon_days + 1):
        day = (now + timedelta(days=offset)).date()
        if not policy.day_allowed(day):
            continue
        opens = datetime.combine(day, start, tzinfo=now.tzinfo)
        closes = datetime.combine(day, end, tzinfo=now.tzinfo)
        if offset == 0:
            if now >= closes:
                continue
            return max(now, opens)
        return opens
    return None


def under_caps(sent_today: int, sent_this_week: int, policy: ReminderPolicy) -> bool:
    return sent_today < policy.max_per_day and sent_this_week < policy.max_per_week
