"""The offline rules behind the helpers (always available, also the fallback when Groq is down)."""

from datetime import date

from app.modules.ai.provider import CourseBrief, RubricPoint
from app.modules.ai.rules_provider import RulesProvider, _parse_due

TODAY = date(2026, 10, 10)


def test_due_dates_in_plain_words() -> None:
    assert _parse_due("by 30 nov", TODAY) == "2026-11-30"
    assert _parse_due("due november 3rd", TODAY) == "2026-11-03"
    assert _parse_due("by 5 jan", TODAY) == "2027-01-05"  # already passed this year -> next year
    assert _parse_due("deadline 2026-12-01", TODAY) == "2026-12-01"
    assert _parse_due("in 2 weeks", TODAY) == "2026-10-24"
    assert _parse_due("end of month", TODAY) == "2026-10-31"
    assert _parse_due("whenever", TODAY) is None


async def test_reading_a_request() -> None:
    request = await RulesProvider().read_request(
        "Assign POSH awareness to everyone in Customer Support by 15 Dec",
        courses=["POSH awareness", "Data privacy basics"],
        departments=["Customer Support", "Sales"],
        roles=["Support Executive"],
        today=TODAY.isoformat(),
    )
    assert request.course == "POSH awareness" and request.department == "Customer Support"
    assert request.everyone is True and request.due_on == "2026-12-15"


async def test_written_scoring_is_sure_only_when_clear() -> None:
    rubric = [RubricPoint("log the refund in the ticket system", 1), RubricPoint("team lead approves big refunds", 1)]
    rules = RulesProvider()
    full = await rules.score_written(
        question="q", model_answer="", rubric=rubric, answer="I log the refund in the ticket system and the team lead approves big refunds"
    )
    assert full.marks == 2 and full.confidence >= 0.7
    blank = await rules.score_written(question="q", model_answer="", rubric=rubric, answer="")
    assert blank.marks == 0 and blank.confidence == 1.0
    partial = await rules.score_written(question="q", model_answer="", rubric=rubric, answer="refund ticket")
    assert partial.confidence < 0.7  # unsure -> a person checks it


async def test_plan_length_follows_the_duration() -> None:
    rules = RulesProvider()
    short = await rules.plan_course(CourseBrief("Fire safety", "All staff", "Know the exits", 15), [])
    long = await rules.plan_course(CourseBrief("Fire safety", "All staff", "Know the exits", 60), [])
    assert len(short.modules) == 3 and len(long.modules) == 6
    assert short.modules[-1].title.startswith("Recap")
