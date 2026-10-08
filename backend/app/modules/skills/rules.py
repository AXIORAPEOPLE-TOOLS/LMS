"""Skills maths from sheet 04. Pure functions: no I/O, easy to test."""

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any


def score_to_level(score: float, bands: Sequence[Sequence[float]]) -> int:
    """bands: [[min_score, level], ...] ascending. Score 68 with default bands -> 3."""
    level = 0
    for min_score, band_level in sorted(bands, key=lambda b: b[0]):
        if score >= min_score:
            level = int(band_level)
    return level


def gap(required_level: int, current_level: int | None) -> int:
    """Required minus current, never below zero. Untested counts as level 0."""
    return max(0, required_level - (current_level or 0))


@dataclass(frozen=True)
class RankEntry:
    key: Any
    score: float
    rank: int
    out_of: int
    top_percent: int  # "Top 25%" means rank is within the best 25%


def stack_rank(scores: Iterable[tuple[Any, float]]) -> list[RankEntry]:
    """Competition ranking (1, 2, 2, 4) highest score first."""
    ordered = sorted(scores, key=lambda s: s[1], reverse=True)
    total = len(ordered)
    entries: list[RankEntry] = []
    previous_score: float | None = None
    previous_rank = 0
    for index, (key, score) in enumerate(ordered, start=1):
        rank = previous_rank if score == previous_score else index
        previous_score, previous_rank = score, rank
        entries.append(RankEntry(key, score, rank, total, top_percent_band(rank, total)))
    return entries


def top_percent_band(rank: int, out_of: int) -> int:
    """Round the share of people at or above this rank up to a friendly band."""
    if out_of <= 0:
        return 100
    share = rank / out_of * 100
    for band in (1, 5, 10, 25, 50, 75):
        if share <= band:
            return band
    return 100


@dataclass(frozen=True)
class Requirement:
    skill_id: Any
    required_level: int
    current_level: int | None  # None = not tested yet


@dataclass(frozen=True)
class Readiness:
    percent: int
    tested: int
    total: int
    total_gap_levels: int
    can_estimate: bool


def readiness(requirements: Sequence[Requirement], min_tested_share: float = 0.5) -> Readiness:
    """Readiness uses only tested skills, so untested skills never count against a person."""
    tested = [r for r in requirements if r.current_level is not None]
    needed = sum(r.required_level for r in tested)
    have = sum(min(r.current_level or 0, r.required_level) for r in tested)
    percent = round(have / needed * 100) if needed else 0
    gaps = sum(gap(r.required_level, r.current_level) for r in tested)
    can_estimate = bool(requirements) and len(tested) / len(requirements) >= min_tested_share
    return Readiness(percent, len(tested), len(requirements), gaps, can_estimate)


def weeks_to_close(gap_levels: int, hours_per_level: float, hours_per_week: float) -> int:
    if gap_levels <= 0 or hours_per_week <= 0:
        return 0
    return math.ceil(gap_levels * hours_per_level / hours_per_week)
