"""Knowledge Hub rules (sheet 14): review status, reminder ladder, health score. Pure functions."""

from dataclasses import dataclass
from datetime import date


def review_status(next_review_on: date | None, today: date, due_soon_days: int, *, status: str = "published") -> str:
    if status == "draft":
        return "draft"
    if status == "in_review":
        return "in_review"
    if status == "archived":
        return "archived"
    if next_review_on is None:
        return "verified"
    if next_review_on < today:
        return "overdue"
    if (next_review_on - today).days <= due_soon_days:
        return "due_soon"
    return "verified"


@dataclass(frozen=True)
class LadderStage:
    number: int
    label: str
    audience: tuple[str, ...]  # owner | backup | function_head | knowledge_admin
    weekly: bool = False


# Days relative to the due date: negative = before, positive = overdue.
LADDER: list[tuple[int, LadderStage]] = [
    (-30, LadderStage(1, "30 days before", ("owner",))),
    (-14, LadderStage(2, "14 days", ("owner", "backup"))),
    (-7, LadderStage(3, "7 days", ("owner",))),
    (0, LadderStage(4, "Due date", ("owner",))),
    (1, LadderStage(5, "Overdue: weekly", ("owner", "backup"), weekly=True)),
    (14, LadderStage(6, "+14 days", ("function_head",))),
    (30, LadderStage(7, "+30 days", ("knowledge_admin",))),
    (90, LadderStage(8, "+90 days", ("knowledge_admin",))),
]


def stages_due(next_review_on: date, today: date) -> list[LadderStage]:
    """Stages that apply today.

    Before the due date only the exact milestone days send (30/14/7/0). While overdue the
    owner and backup hear weekly (day 1, 8, 15...). Escalations (+14, +30, +90) apply from
    that day on; the reminder log makes sure each is sent only once.
    """
    offset = (today - next_review_on).days
    stages: list[LadderStage] = []
    for start, stage in LADDER:
        if stage.weekly:
            if offset >= start and offset % 7 == 1:
                stages.append(stage)
        elif offset == start or (start > 0 and offset >= start):
            stages.append(stage)
    return stages


def excluded_from_answers(next_review_on: date | None, today: date, after_days: int) -> bool:
    return bool(next_review_on and (today - next_review_on).days >= after_days)


@dataclass(frozen=True)
class Health:
    score: int
    items: int
    on_time_pct: int
    overdue: int
    due_soon: int
    no_owner: int
    no_backup: int


def health(statuses: list[tuple[str, bool, bool]], weights: dict[str, float]) -> Health:
    """statuses: (review_status, has_owner, has_backup) per item."""
    total = len(statuses)
    if total == 0:
        return Health(100, 0, 100, 0, 0, 0, 0)
    overdue = sum(1 for s, _, _ in statuses if s == "overdue")
    due_soon = sum(1 for s, _, _ in statuses if s == "due_soon")
    no_owner = sum(1 for _, o, _ in statuses if not o)
    no_backup = sum(1 for _, _, b in statuses if not b)
    on_time = (total - overdue) / total
    score = 100 * (
        weights["on_time"] * on_time
        + weights["owner"] * (total - no_owner) / total
        + weights["backup"] * (total - no_backup) / total
    )
    return Health(round(score), total, round(on_time * 100), overdue, due_soon, no_owner, no_backup)
