"""Gamification maths. Pure functions."""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class ProfileLevel:
    number: int
    name: str
    points: int
    next_name: str | None
    points_to_next: int | None
    progress_pct: int


def profile_level(points: int, levels: Sequence[Sequence[object]]) -> ProfileLevel:
    """levels: [[min_points, name], ...]. 1,240 points -> Practitioner, 260 to Specialist."""
    ordered = sorted(([int(str(p)), str(n)] for p, n in levels), key=lambda x: x[0])
    index = 0
    for i, (min_points, _) in enumerate(ordered):
        if points >= min_points:
            index = i
    current_min, name = ordered[index]
    if index + 1 < len(ordered):
        next_min, next_name = ordered[index + 1]
        span = next_min - current_min
        return ProfileLevel(index + 1, name, points, next_name, next_min - points, round((points - current_min) / span * 100))
    return ProfileLevel(index + 1, name, points, None, None, 100)


def streak_days(activity_days: Iterable[date], today: date) -> int:
    """Consecutive days with learning, ending today (or yesterday, so the day is not lost yet)."""
    days = set(activity_days)
    start = today if today in days else today - timedelta(days=1)
    count = 0
    while start in days:
        count += 1
        start -= timedelta(days=1)
    return count
