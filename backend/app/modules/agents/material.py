"""Company material for the course builder: published, company-wide Knowledge Hub items only."""

import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ai.provider import Passage
from app.modules.knowledge import rules
from app.modules.knowledge.models import ItemStatus, KnowledgeItem, Visibility
from app.modules.settings.service import SettingsService
from app.shared.clock import today

STOP = {"the", "a", "an", "and", "or", "of", "to", "in", "for", "on", "with", "how", "what", "be", "by", "is", "are", "can"}


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOP and len(w) > 2}


async def find_material(session: AsyncSession, topic: str, goal: str, *, limit: int = 4) -> list[Passage]:
    wanted = _words(topic) or _words(goal)
    if not wanted:
        return []
    after = int(await SettingsService(session).get("knowledge.ai_exclusion_overdue_days"))
    items = (
        await session.scalars(
            select(KnowledgeItem).where(
                KnowledgeItem.status == ItemStatus.PUBLISHED.value, KnowledgeItem.visibility == Visibility.COMPANY.value
            )
        )
    ).all()
    scored = []
    for item in items:
        if rules.excluded_from_answers(item.next_review_on, today(), after):
            continue  # long-unreviewed items are not trusted as a source
        title, text = item.title.lower(), (item.body or item.file_text).lower()
        score = sum(3 * title.count(w) + min(text.count(w), 5) for w in wanted)
        if score >= 3:
            scored.append((score, item))
    scored.sort(key=lambda s: s[0], reverse=True)
    return [Passage(i.id, i.title, (i.body or i.file_text)[:4000]) for _, i in scored[:limit]]
