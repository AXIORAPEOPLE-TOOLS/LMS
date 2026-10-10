"""Deterministic, offline implementation. Always available; also the fallback."""

import re
from calendar import monthrange
from datetime import date, timedelta
from difflib import SequenceMatcher

from app.modules.ai.provider import (
    Answer,
    AssignRequest,
    CourseBrief,
    CourseDraft,
    CoursePlan,
    DraftQuestion,
    DraftSection,
    KnowledgeSuggestion,
    LessonText,
    ModuleContent,
    ModulePlan,
    Passage,
    RoleCandidate,
    RoleMatch,
    RubricPoint,
    SourcePage,
    WrittenScore,
)

MODULE_TEMPLATES = [
    ("Why {topic} matters", "Explain why {topic} matters in your work"),
    ("The basics of {topic}", "Describe the key rules and words of {topic}"),
    ("Doing it step by step", "Follow the steps of {topic} in the right order"),
    ("Common mistakes and how to avoid them", "Spot and avoid the usual mistakes"),
    ("A real case from start to finish", "Handle a real case on your own"),
    ("Recap and where to get help", "Know where to find help and what to do next"),
]

MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
EVERYONE_WORDS = ("everyone", "all staff", "all employees", "whole company", "entire company", "all people")

ABBREVIATIONS = {
    "exec": "executive",
    "cs": "customer support",
    "mgr": "manager",
    "sr": "senior",
    "jr": "junior",
    "tl": "team lead",
    "hr": "human resources",
    "ops": "operations",
    "assoc": "associate",
    "rep": "representative",
    "lead": "team lead",
}

KIND_KEYWORDS: dict[str, tuple[str, ...]] = {
    "sop": ("sop", "procedure", "process", "how to", "steps", "workflow"),
    "policy": ("policy", "policies", "rules", "code of conduct", "guidelines"),
    "template": ("template", "format", "letter", "form"),
    "checklist": ("checklist", "check list", "month-end", "list of checks"),
    "playbook": ("playbook", "escalation", "script", "runbook"),
    "faq": ("faq", "questions", "q&a"),
    "meeting_notes": ("minutes", "meeting notes", "mom"),
    "contact_list": ("contacts", "contact list", "directory"),
    "list": ("register", "vendors", "inventory", "tracker"),
}

STOP_WORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "of",
    "to",
    "in",
    "for",
    "on",
    "is",
    "are",
    "do",
    "i",
    "how",
    "what",
    "we",
    "our",
    "with",
    "it",
    "be",
    "by",
    "can",
    "my",
    "your",
    "at",
    "this",
    "that",
}


def _expand(title: str) -> str:
    words = re.findall(r"[a-z0-9]+", title.lower())
    return " ".join(ABBREVIATIONS.get(w, w) for w in words)


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9₹]+", text.lower()) if w not in STOP_WORDS and len(w) > 1}


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [p.strip(" -•\t") for p in parts if len(p.strip()) > 20]


class RulesProvider:
    name = "rules"

    async def match_role(self, job_title: str, candidates: list[RoleCandidate]) -> RoleMatch | None:
        wanted = _expand(job_title)
        best: RoleMatch | None = None
        for candidate in candidates:
            name = candidate.name.lower()
            ratio = SequenceMatcher(None, wanted, name).ratio()
            overlap = len(_tokens(wanted) & _tokens(name)) / max(1, len(_tokens(wanted)))
            score = 0.5 * ratio + 0.5 * overlap
            if best is None or score > best.confidence:
                best = RoleMatch(candidate.id, candidate.name, round(score, 2))
        return best if best and best.confidence >= 0.35 else None

    async def draft_course(
        self, *, pages: list[SourcePage], skill_name: str, include_simulation: bool, quiz_size: int
    ) -> CourseDraft:
        sections: list[DraftSection] = []
        chunks = _group_pages(pages, max_sections=5 if include_simulation else 6)
        for first, last, text in chunks:
            sentences = _sentences(text)
            title = _heading_for(text, fallback=f"Part {len(sections) + 1}")
            summary = " ".join(sentences[:2])[:400] or text[:400]
            ref = f"Source p.{first}" if first == last else f"Source p.{first}–{last}"
            sections.append(DraftSection(title=title, summary=summary, source_ref=ref))
        if include_simulation:
            sections.append(
                DraftSection(
                    title=f"Practice: {skill_name.lower()} in a real case",
                    summary="Do the steps in the right order. Each wrong order shows the reason.",
                    source_ref="Simulation, 5 steps",
                    kind="simulation",
                )
            )
        quiz = _cloze_questions(" ".join(p.text for p in pages), quiz_size)
        return CourseDraft(title=skill_name, sections=sections, quiz=quiz)

    async def suggest_knowledge(self, *, title: str, text: str, kinds: list[str], categories: list[str]) -> KnowledgeSuggestion:
        haystack = f"{title} {text[:2000]}".lower()
        kind = next((k for k, words in KIND_KEYWORDS.items() if k in kinds and any(w in haystack for w in words)), None)
        clean_title = re.sub(r"[_\-]+", " ", re.sub(r"\.(pdf|docx?|xlsx?|txt|md)$", "", title, flags=re.I))
        clean_title = re.sub(r"\b(v\d+(\.\d+)?|final|draft|sop)\b", "", clean_title, flags=re.I).strip()
        category = None
        best = 0.0
        title_tokens = _tokens(haystack)
        for name in categories:
            score = len(_tokens(name) & title_tokens) / max(1, len(_tokens(name)))
            if score > best:
                best, category = score, name
        months = 6 if kind in {"checklist", "list", "contact_list"} else 12
        return KnowledgeSuggestion(
            title=clean_title[:1].upper() + clean_title[1:] if clean_title else title,
            kind=kind or "sop",
            category_name=category,
            review_months=months,
        )

    async def answer(self, question: str, passages: list[Passage]) -> Answer:
        wanted = _tokens(question)
        scored: list[tuple[float, Passage, str]] = []
        for passage in passages:
            for sentence in _sentences(passage.text) or [passage.text]:
                hit = len(wanted & _tokens(sentence)) / max(1, len(wanted))
                if hit > 0:
                    scored.append((hit, passage, sentence))
        if not scored:
            return Answer("I could not find this in the Knowledge Hub. Try other words or ask the owner of the topic.")
        scored.sort(key=lambda s: s[0], reverse=True)
        top = scored[:3]
        cited: list = []
        for _, passage, _ in top:
            if passage.item_id not in cited:
                cited.append(passage.item_id)
        text = " ".join(sentence for _, _, sentence in top)
        return Answer(text=text, cited_item_ids=cited)

    # ---- course builder from a brief --------------------------------------------------------
    async def plan_course(self, brief: CourseBrief, passages: list[Passage]) -> CoursePlan:
        count = max(3, min(len(MODULE_TEMPLATES), brief.duration_minutes // 8))
        # Short courses keep the first steps and the recap; longer ones add the practice parts.
        chosen = [*MODULE_TEMPLATES[: count - 1], MODULE_TEMPLATES[-1]]
        topic = brief.topic.strip()
        modules = [ModulePlan(title=t.format(topic=topic.lower()), outcome=o.format(topic=topic.lower())) for t, o in chosen]
        modules[0] = ModulePlan(title=_capitalise(modules[0].title), outcome=modules[0].outcome)
        description = f"For {brief.audience.strip()}. {_sentence(brief.goal)}"
        return CoursePlan(title=_capitalise(topic), description=description, modules=modules)

    async def write_module(self, brief: CourseBrief, module: ModulePlan, passages: list[Passage]) -> ModuleContent:
        wanted = _tokens(f"{module.title} {module.outcome} {brief.topic}")
        picked: list[tuple[float, str, str]] = []
        for passage in passages:
            for sentence in _sentences(passage.text):
                hit = len(wanted & _tokens(sentence)) / max(1, len(wanted))
                if hit > 0:
                    picked.append((hit, sentence, passage.title))
        picked.sort(key=lambda p: p[0], reverse=True)
        top = picked[:5]
        intro = f"In this part you learn to {module.outcome[:1].lower() + module.outcome[1:]}."
        if top:
            points = "\n".join(f"- {s}" for _, s, _ in top)
            body = f"{intro}\n\n{points}"
            titles = list(dict.fromkeys(t for _, _, t in top))
            source_ref = ("Knowledge Hub: " + ", ".join(titles))[:80]
        else:
            body = (
                f"{intro}\n\n- What it is: the part of {brief.topic.lower()} that {brief.audience.lower()} use every day.\n"
                f"- Why it matters: {_sentence(brief.goal)}\n"
                "- What good looks like: you can do it without help and explain it to a colleague."
            )
            source_ref = "Written from the brief"
        fact = top[0][1] if top else "follows the steps in this part"
        example = (
            f"Example: a colleague in {brief.audience.lower()} needs to {module.outcome[:1].lower() + module.outcome[1:]}. "
            f"They check that it {fact[:1].lower() + fact[1:].rstrip('.')}, then confirm with their team lead before closing it."
        )
        return ModuleContent(body=body, example=example, source_ref=source_ref)

    async def draft_quiz(
        self, *, title: str, goals: list[str], lessons: list[LessonText], choice_count: int, written_count: int
    ) -> list[DraftQuestion]:
        text = " ".join(lesson.text for lesson in lessons)
        questions = _cloze_questions(text, choice_count)
        for lesson in lessons:
            if len([q for q in questions if q.kind == "written"]) >= written_count:
                break
            sentences = [s for s in _sentences(lesson.text) if len(_tokens(s)) >= 3]
            if not sentences:
                continue
            rubric = [RubricPoint(point=s[:160], marks=1) for s in sentences[:3]]
            questions.append(
                DraftQuestion(
                    text=f'Scenario: a new colleague asks you about "{lesson.title}". What would you tell them? '
                    "Give the main points in a few lines.",
                    options=[],
                    answer_index=0,
                    reason="",
                    kind="written",
                    model_answer=" ".join(sentences[:3])[:600],
                    rubric=rubric,
                )
            )
        return questions

    async def score_written(self, *, question: str, model_answer: str, rubric: list[RubricPoint], answer: str) -> WrittenScore:
        points = rubric or [RubricPoint(point=model_answer or question, marks=1)]
        max_marks = sum(max(1, p.marks) for p in points)
        given = _tokens(answer)
        if len(given) < 2:
            return WrittenScore(0, max_marks, 1.0, "No answer was given.")
        marks, met, missed, certainty = 0, [], [], []
        for point in points:
            wanted = _tokens(point.point)
            coverage = len(wanted & given) / max(1, len(wanted))
            if coverage >= 0.5:
                marks += max(1, point.marks)
                met.append(point.point)
            else:
                missed.append(point.point)
            certainty.append(min(1.0, abs(coverage - 0.5) * 2))
        # Matching words is a rough guide, so the rules never claim to be fully sure.
        confidence = round(min(0.9, sum(certainty) / len(certainty)), 2)
        feedback = (
            "You covered the main points." if not missed else "Also mention: " + "; ".join(m[:80] for m in missed[:3]) + "."
        )
        return WrittenScore(marks, max_marks, confidence, feedback, met)

    async def read_request(
        self, text: str, *, courses: list[str], departments: list[str], roles: list[str], today: str
    ) -> AssignRequest:
        lowered = text.lower()
        return AssignRequest(
            course=_best_name(lowered, courses, minimum=0.5),
            department=_best_name(lowered, departments, minimum=0.99),
            job_role=_best_name(lowered, roles, minimum=0.99),
            everyone=any(w in lowered for w in EVERYONE_WORDS),
            due_on=_parse_due(lowered, date.fromisoformat(today)),
        )


def _capitalise(text: str) -> str:
    return text[:1].upper() + text[1:]


def _sentence(text: str) -> str:
    clean = text.strip()
    return _capitalise(clean) + ("" if clean.endswith((".", "!", "?")) else ".")


def _best_name(text: str, names: list[str], *, minimum: float) -> str | None:
    """Name whose words appear in the text (all words for departments/roles, most for courses)."""
    given = _tokens(text)
    best, best_score = None, 0.0
    for name in names:
        wanted = _tokens(name)
        if not wanted:
            continue
        score = len(wanted & given) / len(wanted)
        if name.lower() in text:
            score = 1.0 + len(name) / 1000  # the full name wins; longer exact names beat shorter ones
        if score > best_score:
            best, best_score = name, score
    return best if best_score >= minimum else None


def _parse_due(text: str, today: date) -> str | None:
    if m := re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", text):
        return date(int(m[1]), int(m[2]), int(m[3])).isoformat()
    month_names = "|".join(MONTHS)
    day_month = re.search(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({month_names})[a-z]*\.?(?:\s+(\d{{4}}))?", text)
    month_day = re.search(rf"\b({month_names})[a-z]*\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s+(\d{{4}}))?", text)
    found = None
    if day_month:
        found = (int(day_month[1]), MONTHS[day_month[2]], day_month[3])
    elif month_day:
        found = (int(month_day[2]), MONTHS[month_day[1]], month_day[3])
    if found:
        day, month, year = found
        candidate = date(int(year) if year else today.year, month, min(day, monthrange(today.year, month)[1]))
        if not year and candidate < today:
            candidate = candidate.replace(year=today.year + 1)
        return candidate.isoformat()
    if m := re.search(r"\bin\s+(\d+)\s+(day|week|month)s?\b", text):
        days = int(m[1]) * {"day": 1, "week": 7, "month": 30}[m[2]]
        return (today + timedelta(days=days)).isoformat()
    if "next week" in text:
        return (today + timedelta(days=7)).isoformat()
    if "end of month" in text or "end of the month" in text:
        return today.replace(day=monthrange(today.year, today.month)[1]).isoformat()
    if "tomorrow" in text:
        return (today + timedelta(days=1)).isoformat()
    return None


def _group_pages(pages: list[SourcePage], max_sections: int) -> list[tuple[int, int, str]]:
    usable = [p for p in pages if p.text.strip()]
    if not usable:
        return []
    size = max(1, -(-len(usable) // max_sections))
    groups = []
    for i in range(0, len(usable), size):
        chunk = usable[i : i + size]
        groups.append((chunk[0].page, chunk[-1].page, "\n".join(p.text for p in chunk)))
    return groups


def _heading_for(text: str, fallback: str) -> str:
    for line in text.splitlines():
        clean = line.strip(" #*-•\t0123456789.")
        if 3 <= len(clean) <= 60 and not clean.endswith("."):
            return clean[:1].upper() + clean[1:]
    return fallback


def _cloze_questions(text: str, size: int) -> list[DraftQuestion]:
    """Turn factual sentences into 'which word is missing' questions."""
    sentences = [s for s in _sentences(text) if 30 <= len(s) <= 220]
    vocabulary: list[str] = sorted({w for w in re.findall(r"[A-Za-z₹0-9][\w,₹]{3,}", text) if w.lower() not in STOP_WORDS})
    questions: list[DraftQuestion] = []
    for sentence in sentences:
        words: list[str] = [w for w in re.findall(r"[A-Za-z₹0-9][\w,₹]{3,}", sentence) if w.lower() not in STOP_WORDS]
        if not words:
            continue
        answer: str = max(words, key=len)
        distractors = [w for w in vocabulary if w != answer][:: max(1, len(vocabulary) // 7 or 1)][:3]
        if len(distractors) < 3:
            continue
        position = len(questions) % 4
        options = [*distractors[:position], answer, *distractors[position:3]]
        questions.append(
            DraftQuestion(
                text=f"Fill the gap: {sentence.replace(answer, '_____', 1)}",
                options=options,
                answer_index=position,
                reason=f'The source says: "{sentence}"',
            )
        )
        if len(questions) >= size:
            break
    return questions
