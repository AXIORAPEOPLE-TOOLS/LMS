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
class DraftQuestion:
    text: str
    options: list[str]
    answer_index: int
    reason: str


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


class AssistantProvider(Protocol):
    name: str

    async def match_role(self, job_title: str, candidates: list[RoleCandidate]) -> RoleMatch | None: ...

    async def draft_course(
        self, *, pages: list[SourcePage], skill_name: str, include_simulation: bool, quiz_size: int
    ) -> CourseDraft: ...

    async def suggest_knowledge(
        self, *, title: str, text: str, kinds: list[str], categories: list[str]
    ) -> KnowledgeSuggestion: ...

    async def answer(self, question: str, passages: list[Passage]) -> Answer: ...
