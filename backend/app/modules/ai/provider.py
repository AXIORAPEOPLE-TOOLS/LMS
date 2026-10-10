"""Contract for the assistant service used by courses, people upload and the Knowledge Hub.

Callers depend on `AssistantProvider` only (dependency inversion). Golden rule 5
applies to every result: these are *suggestions*; a person approves them.
"""

from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True)
class RoleCandidate:
    id: UUID
    name: str


@dataclass(frozen=True)
class RoleMatch:
    role_id: UUID
    role_name: str
    confidence: float  # 0..1


@dataclass(frozen=True)
class DraftSection:
    title: str
    summary: str
    source_ref: str
    kind: str = "lesson"  # lesson | simulation


@dataclass(frozen=True)
class RubricPoint:
    point: str
    marks: int = 1


@dataclass(frozen=True)
class DraftQuestion:
    text: str
    options: list[str]
    answer_index: int
    reason: str
    kind: str = "choice"  # choice | written
    model_answer: str = ""
    rubric: list[RubricPoint] = field(default_factory=list)


@dataclass(frozen=True)
class CourseDraft:
    title: str
    sections: list[DraftSection]
    quiz: list[DraftQuestion]


@dataclass(frozen=True)
class KnowledgeSuggestion:
    title: str
    kind: str
    category_name: str | None
    review_months: int


@dataclass(frozen=True)
class Passage:
    item_id: UUID
    title: str
    text: str


@dataclass(frozen=True)
class Answer:
    text: str
    cited_item_ids: list[UUID] = field(default_factory=list)


@dataclass(frozen=True)
class SourcePage:
    page: int
    text: str


@dataclass(frozen=True)
class CourseBrief:
    """What HR gives the course builder (LMS.pdf Course Creation, step 1)."""

    topic: str
    audience: str
    goal: str
    duration_minutes: int


@dataclass(frozen=True)
class ModulePlan:
    title: str
    outcome: str  # what the learner will be able to do


@dataclass(frozen=True)
class CoursePlan:
    title: str
    description: str
    modules: list[ModulePlan]


@dataclass(frozen=True)
class ModuleContent:
    body: str
    example: str
    source_ref: str = ""


@dataclass(frozen=True)
class LessonText:
    title: str
    text: str


@dataclass(frozen=True)
class WrittenScore:
    marks: int
    max_marks: int
    confidence: float  # 0..1; below the setting a person checks it
    feedback: str
    points_met: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AssignRequest:
    """A plain-words training request read into fields; every field may be missing."""

    course: str | None = None
    department: str | None = None
    job_role: str | None = None
    everyone: bool = False
    due_on: str | None = None  # YYYY-MM-DD


class AssistantProvider(Protocol):
    name: str

    async def plan_course(self, brief: CourseBrief, passages: list[Passage]) -> CoursePlan: ...

    async def write_module(self, brief: CourseBrief, module: ModulePlan, passages: list[Passage]) -> ModuleContent: ...

    async def draft_quiz(
        self, *, title: str, goals: list[str], lessons: list[LessonText], choice_count: int, written_count: int
    ) -> list[DraftQuestion]: ...

    async def score_written(
        self, *, question: str, model_answer: str, rubric: list[RubricPoint], answer: str
    ) -> WrittenScore: ...

    async def read_request(
        self, text: str, *, courses: list[str], departments: list[str], roles: list[str], today: str
    ) -> AssignRequest: ...

    async def match_role(self, job_title: str, candidates: list[RoleCandidate]) -> RoleMatch | None: ...

    async def draft_course(
        self, *, pages: list[SourcePage], skill_name: str, include_simulation: bool, quiz_size: int
    ) -> CourseDraft: ...

    async def suggest_knowledge(
        self, *, title: str, text: str, kinds: list[str], categories: list[str]
    ) -> KnowledgeSuggestion: ...

    async def answer(self, question: str, passages: list[Passage]) -> Answer: ...
