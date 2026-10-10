"""Groq-backed provider. Every call falls back to the rules provider on failure,
so the product keeps working if the API is slow, down or returns bad JSON."""

import json
import logging
from typing import Any

from groq import AsyncGroq

from app.core.resilience import breaker
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

    @staticmethod
    def _material(passages: list[Passage]) -> str:
        if not passages:
            return "COMPANY MATERIAL: none. Write general good practice and keep it short."
        return "COMPANY MATERIAL (prefer these facts):\n" + "\n\n".join(f"[{p.title}]\n{p.text[:2000]}" for p in passages[:4])

    async def plan_course(self, brief: CourseBrief, passages: list[Passage]) -> CoursePlan:
        try:
            data = await self._json(
                f"Plan a short workplace course.\nTopic: {brief.topic}\nAudience: {brief.audience}\nGoal: {brief.goal}\n"
                f"Length: about {brief.duration_minutes} minutes, so {max(3, min(6, brief.duration_minutes // 8))} modules.\n"
                "For each module give a title and one outcome starting with a verb (what the learner will be able to do).\n"
                'Reply as {"title": str, "description": "one sentence", "modules": [{"title": str, "outcome": str}]}\n\n'
                + self._material(passages),
                max_tokens=1200,
            )
            modules = [ModulePlan(str(m["title"])[:200], str(m["outcome"])[:300]) for m in data["modules"] if m.get("title")]
            if len(modules) < 2:
                raise ValueError("too few modules")
            return CoursePlan(str(data.get("title") or brief.topic)[:200], str(data.get("description", ""))[:500], modules[:6])
        except Exception:
            logger.warning("Groq plan_course failed; using rules", exc_info=True)
            return await self.fallback.plan_course(brief, passages)

    async def write_module(self, brief: CourseBrief, module: ModulePlan, passages: list[Passage]) -> ModuleContent:
        try:
            data = await self._json(
                f"Write one module of a course on '{brief.topic}' for {brief.audience}.\n"
                f"Module: {module.title}\nOutcome: {module.outcome}\n"
                "Write 120-220 words of plain text with short bullet lines starting with '- ', then one short "
                "workplace example. Name the material you used, if any.\n"
                'Reply as {"body": str, "example": str, "source": "material title or empty"}\n\n' + self._material(passages),
                max_tokens=1200,
            )
            body = str(data.get("body", "")).strip()
            if len(body) < 40:
                raise ValueError("body too short")
            source = str(data.get("source") or "").strip()
            return ModuleContent(body, str(data.get("example", "")).strip(), f"Knowledge Hub: {source}"[:80] if source else "")
        except Exception:
            logger.warning("Groq write_module failed; using rules", exc_info=True)
            return await self.fallback.write_module(brief, module, passages)

    async def draft_quiz(
        self, *, title: str, goals: list[str], lessons: list[LessonText], choice_count: int, written_count: int
    ) -> list[DraftQuestion]:
        try:
            content = "\n\n".join(f"## {lesson.title}\n{lesson.text[:1500]}" for lesson in lessons[:8])
            data = await self._json(
                f"Write a quick check for the course '{title}'. Goals: {json.dumps(goals)}\n"
                f"{choice_count} multiple-choice questions (4 options, index of the right one, one-line reason from the "
                f"content) and {written_count} short workplace scenarios answered in a few lines, each with a model "
                "answer and a rubric of 2-4 points worth 1-2 marks. Mix easy and harder questions. Use only the content.\n"
                'Reply as {"choice": [{"text": str, "options": [str,str,str,str], "answer_index": int, "reason": str}], '
                '"written": [{"text": str, "model_answer": str, "rubric": [{"point": str, "marks": int}]}]}\n\n'
                f"CONTENT:\n{content}",
                max_tokens=4000,
            )
            questions = [
                DraftQuestion(str(q["text"]), list(q["options"])[:4], int(q["answer_index"]), str(q.get("reason", "")))
                for q in data.get("choice", [])
                if len(q.get("options", [])) >= 2
            ][:choice_count]
            questions += [
                DraftQuestion(
                    str(q["text"]),
                    [],
                    0,
                    "",
                    kind="written",
                    model_answer=str(q.get("model_answer", "")),
                    rubric=[RubricPoint(str(r["point"]), int(r.get("marks", 1))) for r in q.get("rubric", []) if r.get("point")],
                )
                for q in data.get("written", [])
            ][:written_count]
            if not questions:
                raise ValueError("no questions")
            return questions
        except Exception:
            logger.warning("Groq draft_quiz failed; using rules", exc_info=True)
            return await self.fallback.draft_quiz(
                title=title, goals=goals, lessons=lessons, choice_count=choice_count, written_count=written_count
            )

    async def score_written(self, *, question: str, model_answer: str, rubric: list[RubricPoint], answer: str) -> WrittenScore:
        if len(answer.strip()) < 3:
            return await self.fallback.score_written(question=question, model_answer=model_answer, rubric=rubric, answer=answer)
        try:
            points = [{"point": p.point, "marks": p.marks} for p in rubric]
            data = await self._json(
                f"Score a written answer against a rubric. Be fair; the meaning counts, not the exact words.\n"
                f"Question: {question}\nModel answer: {model_answer}\nRubric: {json.dumps(points)}\n"
                f"Answer: {answer[:3000]}\n"
                "Give marks per rubric point, one or two sentences of kind feedback, and how sure you are (0..1).\n"
                'Reply as {"points": [{"point": str, "marks": int}], "feedback": str, "confidence": number}',
                max_tokens=600,
            )
            limits = {p.point: max(1, p.marks) for p in rubric}
            given = {str(p.get("point")): int(p.get("marks", 0)) for p in data.get("points", [])}
            marks = sum(max(0, min(limit, given.get(point, 0))) for point, limit in limits.items())
            met = [point for point, limit in limits.items() if given.get(point, 0) >= limit]
            confidence = max(0.0, min(1.0, float(data.get("confidence", 0.5))))
            return WrittenScore(marks, sum(limits.values()), confidence, str(data.get("feedback", "")).strip(), met)
        except Exception:
            logger.warning("Groq score_written failed; using rules", exc_info=True)
            return await self.fallback.score_written(question=question, model_answer=model_answer, rubric=rubric, answer=answer)

    async def read_request(
        self, text: str, *, courses: list[str], departments: list[str], roles: list[str], today: str
    ) -> AssignRequest:
        try:
            data = await self._json(
                f"Today is {today}. Read this training request into fields.\nRequest: {text[:500]}\n"
                f"Courses: {json.dumps(courses[:200])}\nDepartments: {json.dumps(departments)}\n"
                f"Roles: {json.dumps(roles[:200])}\n"
                "Use exact names from the lists or null. due_on as YYYY-MM-DD or null.\n"
                'Reply as {"course": str|null, "department": str|null, "job_role": str|null, "everyone": bool, '
                '"due_on": str|null}',
                max_tokens=300,
            )
            return AssignRequest(
                course=data.get("course") if data.get("course") in courses else None,
                department=data.get("department") if data.get("department") in departments else None,
                job_role=data.get("job_role") if data.get("job_role") in roles else None,
                everyone=bool(data.get("everyone")),
                due_on=str(data["due_on"]) if data.get("due_on") else None,
            )
        except Exception:
            logger.warning("Groq read_request failed; using rules", exc_info=True)
            return await self.fallback.read_request(text, courses=courses, departments=departments, roles=roles, today=today)
