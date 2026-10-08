"""Review reminder ladder (K-10): one combined message per person per day, until it is done."""

from collections import defaultdict
from datetime import time
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.models import User
from app.modules.knowledge import rules
from app.modules.knowledge.models import ItemStatus, KnowledgeItem, KnowledgeReminderLog
from app.modules.knowledge.presenter import Presenter
from app.modules.notifications.models import NotificationKind
from app.modules.notifications.service import NotificationService
from app.modules.scheduler.registry import scheduled_task
from app.shared.clock import today


def _line(item: KnowledgeItem, stage: rules.LadderStage) -> str:
    assert item.next_review_on is not None
    days = (item.next_review_on - today()).days
    if stage.number == 8:
        return f"{item.title}: overdue {-days} days, archive suggested"
    if days > 0:
        return f"{item.title}: due in {days} days"
    if days == 0:
        return f"{item.title}: due today"
    return f"{item.title}: overdue {-days} days"


async def run_ladder(session: AsyncSession) -> int:
    items = (
        await session.scalars(
            select(KnowledgeItem).where(
                KnowledgeItem.status == ItemStatus.PUBLISHED.value, KnowledgeItem.next_review_on.is_not(None)
            )
        )
    ).all()
    tree = await Presenter(session).tree()
    knowledge_admins = [
        u.id for u in (await session.scalars(select(User).where(User.is_active.is_(True)))).all() if u.has_role("knowledge_admin")
    ]
    sent_logs = {
        (log.item_id, log.due_on, log.stage, log.period_key)
        for log in (await session.scalars(select(KnowledgeReminderLog))).all()
    }
    messages: dict[UUID, list[str]] = defaultdict(list)
    as_owner: set[UUID] = set()
    week = today().strftime("%G-W%V")
    for item in items:
        assert item.next_review_on is not None
        for stage in rules.stages_due(item.next_review_on, today()):
            period = week if stage.weekly else ""
            key = (item.id, item.next_review_on, stage.number, period)
            if key in sent_logs:
                continue
            session.add(KnowledgeReminderLog(item_id=item.id, due_on=item.next_review_on, stage=stage.number, period_key=period))
            sent_logs.add(key)
            recipients: set[UUID] = set()
            if "owner" in stage.audience and item.owner_id:
                recipients.add(item.owner_id)
                as_owner.add(item.owner_id)
            if "backup" in stage.audience and item.backup_owner_id:
                recipients.add(item.backup_owner_id)
            if "function_head" in stage.audience:
                root = tree.by_id.get(tree.root_of(item.category_id)) if item.category_id else None
                if root and root.head_id:
                    recipients.add(root.head_id)
            if "knowledge_admin" in stage.audience or not item.owner_id:
                recipients.update(knowledge_admins)
            for person in recipients:
                messages[person].append(_line(item, stage))
    notifications = NotificationService(session)
    sent = 0
    names = (
        dict((await session.execute(select(User.id, User.full_name).where(User.id.in_(list(messages))))).all())
        if messages
        else {}
    )
    for person, lines in messages.items():
        first = (names.get(person) or "there").split()[0]
        unique = list(dict.fromkeys(lines))
        body = f"Hi {first}, {len(unique)} item{'s' if len(unique) != 1 else ''} need{'s' if len(unique) == 1 else ''} a look:\n"
        body += "\n".join(f"• {line}" for line in unique[:15])
        if person in as_owner:
            body += "\nIt takes one click if nothing has changed."
        result = await notifications.notify(
            person,
            kind=NotificationKind.KNOWLEDGE,
            title="Knowledge items to review",
            body=body,
            link="/knowledge/my-items",
            actions=[{"label": "Open My items", "href": "/knowledge/my-items"}],
            automatic=True,
        )
        sent += 1 if result else 0
    return sent


@scheduled_task("knowledge.review_ladder", "daily", not_before=time(9, 0))
async def ladder_task(session: AsyncSession) -> int:
    return await run_ladder(session)
