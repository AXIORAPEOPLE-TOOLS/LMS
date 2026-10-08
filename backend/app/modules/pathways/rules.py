"""Pathway rules (sheet 04): gaps -> ordered waves of N skills. Pure functions."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GapInput:
    skill_id: Any
    skill_name: str
    required_level: int
    current_level: int | None
    is_mandatory: bool = False

    @property
    def gap(self) -> int:
        return max(0, self.required_level - (self.current_level or 0))


@dataclass(frozen=True)
class PlannedItem:
    wave: int
    position: int
    skill_id: Any
    from_level: int
    to_level: int
    estimated_hours: float


def plan_waves(gaps: Sequence[GapInput], *, wave_size: int, hours_per_level: float) -> list[PlannedItem]:
    """Mandatory skills first, then the biggest gaps, then by name (stable and explainable)."""
    open_gaps = [g for g in gaps if g.gap > 0]
    ordered = sorted(open_gaps, key=lambda g: (not g.is_mandatory, -g.gap, g.skill_name))
    items: list[PlannedItem] = []
    for index, g in enumerate(ordered):
        items.append(
            PlannedItem(
                wave=index // wave_size + 1,
                position=index % wave_size + 1,
                skill_id=g.skill_id,
                from_level=g.current_level or 0,
                to_level=g.required_level,
                estimated_hours=round(g.gap * hours_per_level, 1),
            )
        )
    return items


def wave_weeks(hours: float, hours_per_week: float) -> int:
    import math

    return max(1, math.ceil(hours / hours_per_week)) if hours_per_week > 0 else 0
