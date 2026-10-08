"""Deterministic, offline implementation. Always available; also the fallback."""

import re
from difflib import SequenceMatcher

from app.modules.ai.provider import (
    Answer,
    CourseDraft,
    DraftQuestion,
    DraftSection,
    KnowledgeSuggestion,
    Passage,
    RoleCandidate,
    RoleMatch,
    SourcePage,
)

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
    vocabulary = sorted({w for w in re.findall(r"[A-Za-z₹0-9][\w,₹]{3,}", text) if w.lower() not in STOP_WORDS})
    questions: list[DraftQuestion] = []
    for sentence in sentences:
        words = [w for w in re.findall(r"[A-Za-z₹0-9][\w,₹]{3,}", sentence) if w.lower() not in STOP_WORDS]
        if not words:
            continue
        answer = max(words, key=len)
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
