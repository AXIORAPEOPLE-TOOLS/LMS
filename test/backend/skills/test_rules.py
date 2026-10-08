"""Sheet 04 maths. Expected numbers come from the UI deck examples."""

import pytest

from app.modules.settings.defaults import DEFAULTS
from app.modules.skills import rules

BANDS = DEFAULTS["skills.level_bands"][0]


@pytest.mark.parametrize(
    ("score", "level"),
    [(0, 0), (19, 0), (20, 1), (45, 2), (68, 3), (72, 3), (77, 4), (88, 4), (92, 5), (100, 5)],
)
def test_score_to_level_matches_deck(score: int, level: int) -> None:
    assert rules.score_to_level(score, BANDS) == level


def test_gap_never_below_zero_and_untested_counts_as_zero() -> None:
    assert rules.gap(3, 1) == 2
    assert rules.gap(2, 4) == 0
    assert rules.gap(2, None) == 2


def test_stack_rank_uses_competition_ranking() -> None:
    entries = rules.stack_rank([("a", 90), ("b", 80), ("c", 80), ("d", 70)])
    assert [(e.key, e.rank) for e in entries] == [("a", 1), ("b", 2), ("c", 2), ("d", 4)]
    assert all(e.out_of == 4 for e in entries)


def test_top_percent_band() -> None:
    assert rules.top_percent_band(9, 36) == 25  # deck: "Top 25% of 36 people tested"
    assert rules.top_percent_band(1, 100) == 1
    assert rules.top_percent_band(36, 36) == 100


def test_readiness_ignores_untested_skills() -> None:
    reqs = [
        rules.Requirement("a", 3, 3),
        rules.Requirement("b", 3, 1),
        rules.Requirement("c", 2, None),  # not tested: never counts against the person
    ]
    result = rules.readiness(reqs)
    assert result.percent == round(4 / 6 * 100)
    assert (result.tested, result.total, result.total_gap_levels) == (2, 3, 2)


def test_weeks_to_close() -> None:
    assert rules.weeks_to_close(5, 1.8, 3) == 3
    assert rules.weeks_to_close(0, 1.8, 3) == 0
