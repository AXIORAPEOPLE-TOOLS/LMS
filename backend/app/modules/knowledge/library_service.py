"""Find things: Home (K-01), Library (K-07), search/ask, My items (K-09), bulk actions."""

import re
from collections import Counter
from datetime import timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import PermissionDeniedError, ValidationFailedError
from app.modules.ai.provider import Passage
from app.modules.ai.service import get_assistant
from app.modules.audit.service import AuditService
from app.modules.identity.models import User
from app.modules.knowledge import rules
from app.modules.knowledge.models import (
    KIND_LABELS,
    ItemStatus,
    KnowledgeItem,
    KnowledgeRevision,
    KnowledgeSearchLog,
)
from app.modules.knowledge.permissions import KnowledgePolicy, is_knowledge_admin
from app.modules.knowledge.presenter import Presenter
from app.modules.knowledge.schemas import (
    AnswerOut,
    BulkIn,
    CategoryOut,
    HomeOut,
    ItemSummaryOut,
    MyItemOut,
    MyItemsOut,
    SearchHitOut,
)
from app.modules.notifications.models import NotificationKind
from app.modules.notifications.service import NotificationService
from app.modules.settings.service import SettingsService
from app.shared.clock import today, utcnow

STOP = {"the", "a", "an", "and", "or", "of", "to", "in", "for", "on", "is", "how", "do", "i", "what", "we", "my", "our"}


def _tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9₹]+", text.lower()) if t not in STOP and len(t) > 1]


class LibraryService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.policy = KnowledgePolicy(session)
        self.presenter = Presenter(session)

    async def _readable(self, user: User, *extra: Any) -> list[KnowledgeItem]:
        stmt = select(KnowledgeItem).where(self.policy.readable_filter(user), *extra)
        return list((await self.session.scalars(stmt)).all())

    # ---- Library ----------------------------------------------------------------------
    async def library(
        self,
        user: User,
        *,
        category_id: UUID | None = None,
        kind: str | None = None,
        status: str | None = None,
        owner_id: UUID | None = None,
        critical: bool | None = None,
        q: str | None = None,
        sort: str = "title",
    ) -> dict[str, Any]:
        items = await self._readable(user, KnowledgeItem.status != ItemStatus.ARCHIVED.value)
        tree = await self.presenter.tree()
        summaries = await self.presenter.summaries(items)
        by_id = {i.id: i for i in items}
        kind_counts = Counter(s.kind for s in summaries)
        category_counts: Counter[UUID] = Counter()
        for s in summaries:
            cid = s.category_id
            while cid:
                category_counts[cid] += 1
                parent = tree.by_id.get(cid)
                cid = parent.parent_id if parent else None
        rows = summaries
        if category_id:
            allowed = tree.descendants(category_id)
            rows = [r for r in rows if r.category_id in allowed]
        if kind:
            rows = [r for r in rows if r.kind == kind]
        if status:
            rows = [r for r in rows if r.status == status]
        if owner_id:
            rows = [r for r in rows if r.owner_id == owner_id]
        if critical is not None:
            rows = [r for r in rows if r.is_critical == critical]
        if q:
            words = _tokens(q)
            rows = [r for r in rows if all(w in (r.title + " " + by_id[r.id].body).lower() for w in words)]
        order = {
            "title": lambda r: r.title.lower(),
            "next_review": lambda r: (r.next_review_on is None, r.next_review_on),
            "updated": lambda r: -r.updated_at.timestamp(),
        }.get(sort, lambda r: r.title.lower())
        rows = sorted(rows, key=order)  # type: ignore[arg-type]
        categories = [
            CategoryOut(
                id=c.id,
                name=c.name,
                parent_id=c.parent_id,
                head_id=c.head_id,
                position=c.position,
                item_count=category_counts.get(c.id, 0),
                path=tree.path(c.id) or c.name,
            )
            for c in sorted(tree.by_id.values(), key=lambda c: tree.path(c.id) or "")
        ]
        return {
            "total": len(summaries),
            "items": rows,
            "kinds": [{"kind": k, "label": KIND_LABELS.get(k, k), "count": n} for k, n in kind_counts.most_common()],
            "categories": categories,
        }

    # ---- Home (K-01) -----------------------------------------------------------------------
    async def home(self, user: User) -> HomeOut:
        library = await self.library(user)
        rows: list[ItemSummaryOut] = library["items"]
        verified = sorted((r for r in rows if r.status == "verified"), key=lambda r: r.updated_at, reverse=True)[:5]
        critical = [r for r in rows if r.is_critical][:6]
        spaces = [c for c in library["categories"] if c.parent_id is None]
        return HomeOut(
            types=library["kinds"],
            spaces=spaces,
            recently_verified=verified,
            critical=critical,
            my_items=await self.my_items(user),
        )

    # ---- search & ask ----------------------------------------------------------------------
    async def search(self, user: User, query: str, *, limit: int = 20) -> list[SearchHitOut]:
        words = _tokens(query)
        if not words:
            raise ValidationFailedError("Type a few words to search.")
        items = await self._readable(user, KnowledgeItem.status != ItemStatus.ARCHIVED.value)
        scored: list[tuple[float, KnowledgeItem, str]] = []
        for item in items:
            title, body, files = item.title.lower(), item.body.lower(), item.file_text.lower()
            score = sum(3 * title.count(w) + min(body.count(w), 5) + 0.5 * min(files.count(w), 5) for w in words)
            if all(w in title + " " + body + " " + files for w in words):
                score *= 1.5
            if score > 0:
                scored.append((score, item, _snippet(item.body or item.file_text, words)))
        scored.sort(key=lambda s: s[0], reverse=True)
        top = scored[:limit]
        summaries = await self.presenter.summaries([i for _, i, _ in top])
        self.session.add(
            KnowledgeSearchLog(
                user_id=user.id, query=query[:300], results=len(scored), top_category_id=top[0][1].category_id if top else None
            )
        )
        return [
            SearchHitOut(item=s, snippet=snip, score=round(score, 1)) for s, (score, _, snip) in zip(summaries, top, strict=True)
        ]

    async def ask(self, user: User, question: str) -> AnswerOut:
        words = _tokens(question)
        if not words:
            raise ValidationFailedError("Ask a question in a few words.")
        after = int(await SettingsService(self.session).get("knowledge.ai_exclusion_overdue_days"))
        items = [
            i
            for i in await self._readable(user, KnowledgeItem.status == ItemStatus.PUBLISHED.value)
            # Items left unreviewed too long are left out of answers (ladder stage 7).
            if not rules.excluded_from_answers(i.next_review_on, today(), after)
        ]
        ranked = sorted(
            items,
            key=lambda i: -sum(3 * i.title.lower().count(w) + (i.body + i.file_text).lower().count(w) for w in words),
        )
        passages = [
            Passage(i.id, i.title, (i.body or i.file_text)[:4000])
            for i in ranked[:5]
            if any(w in (i.title + i.body + i.file_text).lower() for w in words)
        ]
        answer = await get_assistant().answer(question, passages)
        by_id = {i.id: i for i in items}
        sources = await self.presenter.summaries([by_id[i] for i in answer.cited_item_ids if i in by_id])
        self.session.add(
            KnowledgeSearchLog(
                user_id=user.id,
                query=question[:300],
                mode="ask",
                results=len(sources),
                top_category_id=sources[0].category_id if sources else None,
            )
        )
        return AnswerOut(answer=answer.text, sources=sources)

    # ---- My items (K-09) ------------------------------------------------------------------------
    async def my_items(self, user: User) -> MyItemsOut:
        owned = (
            await self.session.scalars(
                select(KnowledgeItem).where(
                    (KnowledgeItem.owner_id == user.id) | (KnowledgeItem.backup_owner_id == user.id),
                    KnowledgeItem.status != ItemStatus.ARCHIVED.value,
                )
            )
        ).all()
        summaries = {s.id: s for s in await self.presenter.summaries(owned)}
        max_snoozes = int(await SettingsService(self.session).get("knowledge.max_snoozes"))
        out: list[MyItemOut] = []
        for item in owned:
            s = summaries[item.id]
            if item.owner_id != user.id:
                continue
            if s.status == "overdue" and item.next_review_on:
                days = (today() - item.next_review_on).days
                out.append(
                    MyItemOut(
                        item=s,
                        reason="overdue",
                        detail=f"Overdue {days} day{'s' if days != 1 else ''}",
                        can_snooze=item.snooze_count < max_snoozes,
                    )
                )
            elif s.status == "due_soon" and item.next_review_on:
                days = (item.next_review_on - today()).days
                out.append(
                    MyItemOut(
                        item=s,
                        reason="due_soon",
                        detail=f"Due in {days} day{'s' if days != 1 else ''}",
                        can_snooze=item.snooze_count < max_snoozes,
                    )
                )
        waiting = (
            await self.session.execute(
                select(KnowledgeRevision, KnowledgeItem)
                .join(KnowledgeItem, KnowledgeItem.id == KnowledgeRevision.item_id)
                .where(KnowledgeRevision.status == "submitted", KnowledgeItem.owner_id == user.id)
            )
        ).all()
        names = await self.presenter.names({r.author_id for r, _ in waiting})
        waiting_summaries = await self.presenter.summaries([i for _, i in waiting])
        for (revision, _), s in zip(waiting, waiting_summaries, strict=True):
            author = names.get(revision.author_id, "someone") if revision.author_id else "someone"
            out.append(
                MyItemOut(
                    item=s.model_copy(update={"title": f"{s.title}: change by {author}"}),
                    reason="waiting_for_me",
                    detail="Waiting for my approval",
                    revision_id=revision.id,
                    can_snooze=False,
                )
            )
        drafts = (
            await self.session.execute(
                select(KnowledgeRevision, KnowledgeItem)
                .join(KnowledgeItem, KnowledgeItem.id == KnowledgeRevision.item_id)
                .where(KnowledgeRevision.status == "draft", KnowledgeRevision.author_id == user.id)
            )
        ).all()
        draft_summaries = await self.presenter.summaries([i for _, i in drafts])
        for (revision, _), s in zip(drafts, draft_summaries, strict=True):
            days = (today() - revision.updated_at.date()).days
            out.append(
                MyItemOut(
                    item=s, reason="draft", detail=f"Draft untouched for {days} days", revision_id=revision.id, can_snooze=False
                )
            )
        order = {"overdue": 0, "due_soon": 1, "waiting_for_me": 2, "draft": 3}
        out.sort(key=lambda m: (order[m.reason], m.item.next_review_on or today()))
        coming = [
            {"when": _when(item.next_review_on), "text": f"{item.title}: due date"}
            for item in sorted(
                (i for i in owned if i.next_review_on and i.next_review_on >= today() and i.owner_id == user.id),
                key=lambda i: i.next_review_on or today(),
            )[:3]
        ]
        backups = {i.backup_owner_id for i in owned if i.owner_id == user.id and i.backup_owner_id}
        backup_names = await self.presenter.names(backups)
        backup_note = (
            (
                f"{', '.join(sorted(backup_names.values()))} "
                f"{'is' if len(backup_names) == 1 else 'are'} copied from 14 days before each review."
            )
            if backup_names
            else None
        )
        counts = Counter(m.reason for m in out)
        return MyItemsOut(
            overdue=counts["overdue"],
            due_soon=counts["due_soon"],
            waiting_for_me=counts["waiting_for_me"],
            drafts=counts["draft"],
            items=out,
            coming_up=coming,
            backup_note=backup_note,
        )

    # ---- bulk actions (K-07) -------------------------------------------------------------------
    async def bulk(self, user: User, data: BulkIn) -> int:
        if not is_knowledge_admin(user) and not user.has_role("function_head"):
            raise PermissionDeniedError("Only knowledge admins and function heads can change many items at once.")
        items = (await self.session.scalars(select(KnowledgeItem).where(KnowledgeItem.id.in_(data.item_ids)))).all()
        if data.action == "remind_owners":
            by_owner: dict[UUID, list[str]] = {}
            for item in items:
                if item.owner_id:
                    by_owner.setdefault(item.owner_id, []).append(item.title)
            for owner_id, titles in by_owner.items():  # combined: one message per owner
                await NotificationService(self.session).notify(
                    owner_id,
                    kind=NotificationKind.KNOWLEDGE,
                    title=f"{len(titles)} of your items need a look",
                    body="\n".join(f"• {t}" for t in titles[:10]),
                    link="/knowledge/my-items",
                )
        elif data.action == "change_owner":
            if not data.owner_id:
                raise ValidationFailedError("Choose the new owner.")
            for item in items:
                item.owner_id = data.owner_id
        elif data.action == "set_review_date":
            if not data.review_on:
                raise ValidationFailedError("Choose the review date.")
            for item in items:
                item.next_review_on = data.review_on
        elif data.action == "change_category":
            for item in items:
                item.category_id = data.category_id
        AuditService(self.session).record(
            f"knowledge.bulk_{data.action}", "knowledge_item", None, actor_id=user.id, count=len(items)
        )
        return len(items)

    async def search_success(self, since_days: int = 90) -> dict[UUID | None, tuple[int, int]]:
        rows = (
            await self.session.execute(
                select(KnowledgeSearchLog.top_category_id, func.count(), func.count().filter(KnowledgeSearchLog.results > 0))
                .where(KnowledgeSearchLog.created_at >= utcnow() - timedelta(days=since_days))
                .group_by(KnowledgeSearchLog.top_category_id)
            )
        ).all()
        return {cid: (total, found) for cid, total, found in rows}


def _snippet(text: str, words: list[str], width: int = 180) -> str:
    lower = text.lower()
    positions = [lower.find(w) for w in words if lower.find(w) >= 0]
    if not positions:
        return text[:width].strip()
    start = max(0, min(positions) - 40)
    snippet = text[start : start + width].replace("\n", " ").strip()
    return ("…" if start else "") + snippet + ("…" if start + width < len(text) else "")


def _when(day: Any) -> str:
    if day is None:
        return ""
    delta = (day - today()).days
    return "Today" if delta == 0 else f"In {delta} days"
