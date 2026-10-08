"""Groq-backed provider. Every call falls back to the rules provider on failure,
so the product keeps working if the API is slow, down or returns bad JSON."""

import json
import logging
from typing import Any

from groq import AsyncGroq

from app.core.resilience import breaker
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
from app.modules.ai.rules_provider import RulesProvider

logger = logging.getLogger(__name__)

SYSTEM = (
    "You help an internal learning and knowledge platform for a service company. "
    "Use plain, short English. Only use facts from the material given. "
    "Always reply with one JSON object and nothing else."
)


class GroqProvider:
    name = "groq"

    def __init__(self, api_key: str, model: str, timeout: float) -> None:
        self.client = AsyncGroq(api_key=api_key, timeout=timeout, max_retries=1)
        self.model = model
        self.fallback = RulesProvider()

    async def _json(self, prompt: str, max_tokens: int = 2000) -> dict[str, Any]:
        # While Groq keeps failing the breaker is open and callers use the rules fallback at once.
        return await breaker("groq", reset_seconds=60).call(lambda: self._call(prompt, max_tokens))

    async def _call(self, prompt: str, max_tokens: int) -> dict[str, Any]:
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.2,
            max_completion_tokens=max_tokens,
        )
        return json.loads(response.choices[0].message.content or "{}")

    async def match_role(self, job_title: str, candidates: list[RoleCandidate]) -> RoleMatch | None:
        try:
            names = [c.name for c in candidates]
            data = await self._json(
                f'Job title from a spreadsheet: "{job_title}".\nPick the closest role from this list or null.\n'
                f"Roles: {json.dumps(names)}\n"
                'Reply as {"role": "<exact name or null>", "confidence": <0..1>}',
                max_tokens=200,
            )
            by_name = {c.name: c for c in candidates}
            chosen = by_name.get(str(data.get("role")))
            if chosen is None:
                return await self.fallback.match_role(job_title, candidates)
            return RoleMatch(chosen.id, chosen.name, float(data.get("confidence", 0.7)))
        except Exception:
            logger.warning("Groq match_role failed; using rules", exc_info=True)
            return await self.fallback.match_role(job_title, candidates)

    async def draft_course(
        self, *, pages: list[SourcePage], skill_name: str, include_simulation: bool, quiz_size: int
    ) -> CourseDraft:
        try:
            source = "\n".join(f"[page {p.page}] {p.text[:3000]}" for p in pages[:40])
            data = await self._json(
                f"Write a short course outline that teaches the skill '{skill_name}' from this source.\n"
                f"4 to 6 sections, each with title, a two-sentence summary, and the source pages used.\n"
                f"Then {quiz_size} multiple-choice questions with 4 options, the index of the right option "
                "and a one-line reason quoting the source.\n"
                'Reply as {"title": str, "sections": [{"title": str, "summary": str, "pages": "4-5"}], '
                '"quiz": [{"text": str, "options": [str,str,str,str], "answer_index": int, "reason": str}]}\n\n'
                f"SOURCE:\n{source}",
                max_tokens=4000,
            )
            sections = [
                DraftSection(title=s["title"], summary=s["summary"], source_ref=f"Source p.{s.get('pages', '?')}")
                for s in data["sections"]
            ]
            if include_simulation:
                sections.append(
                    DraftSection(
                        title=f"Practice: {skill_name.lower()} in a real case",
                        summary="Do the steps in the right order. Each wrong order shows the reason.",
                        source_ref="Simulation, 5 steps",
                        kind="simulation",
                    )
                )
            quiz = [
                DraftQuestion(q["text"], list(q["options"])[:4], int(q["answer_index"]), q.get("reason", ""))
                for q in data["quiz"]
                if len(q.get("options", [])) >= 2
            ]
            return CourseDraft(title=data.get("title") or skill_name, sections=sections, quiz=quiz[:quiz_size])
        except Exception:
            logger.warning("Groq draft_course failed; using rules", exc_info=True)
            return await self.fallback.draft_course(
                pages=pages, skill_name=skill_name, include_simulation=include_simulation, quiz_size=quiz_size
            )

    async def suggest_knowledge(self, *, title: str, text: str, kinds: list[str], categories: list[str]) -> KnowledgeSuggestion:
        try:
            data = await self._json(
                f"A person is adding '{title}' to the company knowledge base. Text start:\n{text[:2500]}\n\n"
                f"Pick kind from {json.dumps(kinds)} and category from {json.dumps(categories)}. "
                "Suggest a clean title and review months (6 or 12).\n"
                'Reply as {"title": str, "kind": str, "category": str, "review_months": int}',
                max_tokens=300,
            )
            kind = data.get("kind") if data.get("kind") in kinds else "sop"
            category = data.get("category") if data.get("category") in categories else None
            return KnowledgeSuggestion(
                title=str(data.get("title") or title)[:200],
                kind=kind,
                category_name=category,
                review_months=int(data.get("review_months") or 12),
            )
        except Exception:
            logger.warning("Groq suggest_knowledge failed; using rules", exc_info=True)
            return await self.fallback.suggest_knowledge(title=title, text=text, kinds=kinds, categories=categories)

    async def answer(self, question: str, passages: list[Passage]) -> Answer:
        if not passages:
            return await self.fallback.answer(question, passages)
        try:
            numbered = "\n\n".join(f"[{i}] {p.title}\n{p.text[:2500]}" for i, p in enumerate(passages))
            data = await self._json(
                f"Question: {question}\n\nAnswer only from these items. If they do not answer it, say so.\n"
                f"{numbered}\n\n"
                'Reply as {"answer": "2-4 short sentences", "sources": [item numbers used]}',
                max_tokens=600,
            )
            used = [passages[i].item_id for i in data.get("sources", []) if isinstance(i, int) and 0 <= i < len(passages)]
            return Answer(text=str(data.get("answer", "")).strip(), cited_item_ids=used)
        except Exception:
            logger.warning("Groq answer failed; using rules", exc_info=True)
            return await self.fallback.answer(question, passages)
