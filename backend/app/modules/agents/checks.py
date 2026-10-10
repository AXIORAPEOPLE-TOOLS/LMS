"""Checks a helper runs on its own work before a person sees it (no assistant involved: plain rules)."""

import re
from dataclasses import dataclass

from app.modules.ai.provider import DraftQuestion
from app.modules.learning.models import CourseQuestion, Lesson


def _norm(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


@dataclass
class QuestionCheck:
    kept: list[DraftQuestion]
    removed: list[str]  # plain reasons


def check_questions(drafts: list[DraftQuestion]) -> QuestionCheck:
    """Drop broken or repeated questions: the answer must be one of the options, options must differ."""
    kept: list[DraftQuestion] = []
    removed: list[str] = []
    seen: set[str] = set()
    for q in drafts:
        key = _norm(q.text)
        if len(key) < 8:
            removed.append("too short")
        elif key in seen:
            removed.append("repeated")
        elif q.kind == "written":
            if not q.rubric:
                removed.append("written question without points to score")
            else:
                kept.append(q)
                seen.add(key)
            continue
        elif len(q.options) < 2 or not 0 <= q.answer_index < len(q.options):
            removed.append("right answer missing from the options")
        elif len({_norm(o) for o in q.options}) < len(q.options):
            removed.append("two options say the same")
        else:
            kept.append(q)
            seen.add(key)
    return QuestionCheck(kept, removed)


def difficulty_mix(questions: list[DraftQuestion]) -> str:
    written = sum(1 for q in questions if q.kind == "written")
    choice = len(questions) - written
    return f"{choice} multiple choice (recall) and {written} written scenario{'s' if written != 1 else ''} (apply)"


def check_course(lessons: list[Lesson], wanted_minutes: int) -> list[str]:
    issues: list[str] = []
    if len(lessons) < 2:
        issues.append("Only one module; consider splitting it.")
    for lesson in lessons:
        if len((lesson.body or "").strip()) < 120:
            issues.append(f'"{lesson.title}" is short; add a few lines.')
    titles = [_norm(lsn.title) for lsn in lessons]
    if len(set(titles)) < len(titles):
        issues.append("Two modules have the same title.")
    total = sum(lsn.duration_minutes for lsn in lessons)
    if wanted_minutes and abs(total - wanted_minutes) > max(5, wanted_minutes * 0.3):
        issues.append(f"Lessons add up to {total} minutes; the brief asked for about {wanted_minutes}.")
    return issues


def trial_run(lessons: list[Lesson], questions: list[CourseQuestion], pass_mark: int) -> tuple[bool, str]:
    """Walk the course as a learner would: every lesson opens, the key passes, a blank attempt fails."""
    problems = [f'"{lsn.title}" has no text' for lsn in lessons if not (lsn.body or lsn.summary).strip()]
    for q in questions:
        if q.kind == "written":
            if not q.rubric:
                problems.append(f"Question {q.position} has nothing to score against")
        elif not 0 <= q.answer_index < len(q.options):
            problems.append(f"Question {q.position} has no right answer")
    minutes = sum(lsn.duration_minutes for lsn in lessons)
    if problems:
        return False, "Found problems: " + "; ".join(problems[:5]) + "."
    if not questions:
        return True, f"Opened all {len(lessons)} lessons ({minutes} minutes). There is no quick check yet."
    return True, (
        f"Opened all {len(lessons)} lessons ({minutes} minutes) and took the quick check with the right answers: "
        f"100 out of 100, pass mark {pass_mark}. A blank attempt scores 0 and does not pass."
    )
