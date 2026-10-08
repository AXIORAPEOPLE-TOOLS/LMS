"""Knowledge items: add (K-02), page (K-03), versions/revisions/reviews (K-08), owner actions."""

import difflib
import re
import uuid
from collections import Counter
from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import ConflictError, NotFoundError, PermissionDeniedError, ValidationFailedError
from app.modules.ai.service import extract_pages, get_assistant
from app.modules.audit.service import AuditService
from app.modules.certificates.service import add_months
from app.modules.identity.models import Department, User
from app.modules.knowledge.models import (
    KIND_LABELS,
    ItemKind,
    ItemStatus,
    KnowledgeCategory,
    KnowledgeItem,
    KnowledgeReview,
    KnowledgeRevision,
    KnowledgeUpload,
    KnowledgeVersion,
    Visibility,
)
from app.modules.knowledge.permissions import KnowledgePolicy, Rights, is_knowledge_admin
from app.modules.knowledge.presenter import Presenter
from app.modules.knowledge.schemas import (
    CompareOut,
    DiffLineOut,
    HistoryEntryOut,
    ItemIn,
    ItemOut,
    ItemSettingsUpdate,
    ItemUpdate,
    SuggestIn,
    SuggestionOut,
)
from app.modules.notifications.models import NotificationKind
from app.modules.notifications.service import NotificationService
from app.modules.settings.service import SettingsService
from app.shared.clock import today, utcnow

MAX_UPLOAD_BYTES = 25 * 1024 * 1024


class ItemService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.policy = KnowledgePolicy(session)
        self.presenter = Presenter(session)
        self.audit = AuditService(session)
        self.notify = NotificationService(session)

    # ---- reading --------------------------------------------------------------------------
    async def detail(self, item_id: UUID, user: User) -> ItemOut:
        item, rights = await self.policy.get_readable(item_id, user)
        return await self._out(item, rights)

    async def _out(self, item: KnowledgeItem, rights: Rights) -> ItemOut:
        summary = await self.presenter.summary(item)
        names = await self.presenter.names({item.backup_owner_id})
        versions = int(await self.session.scalar(select(func.count()).where(KnowledgeVersion.item_id == item.id)) or 0)
        pending = bool(
            (
                await self.session.scalars(
                    select(KnowledgeRevision.id).where(
                        KnowledgeRevision.item_id == item.id, KnowledgeRevision.status == "submitted"
                    )
                )
            ).first()
        )
        return ItemOut(
            **summary.model_dump(),
            body=item.body,
            link_url=item.link_url,
            attachments=item.attachments,
            backup_owner_id=item.backup_owner_id,
            backup_owner_name=names.get(item.backup_owner_id) if item.backup_owner_id else None,
            team_department_id=item.team_department_id,
            review_months=item.review_months,
            last_verified_at=item.last_verified_at,
            snooze_count=item.snooze_count,
            version_count=versions,
            list_columns=item.list_columns,
            linked_course_id=item.linked_course_id,
            linked_skill_id=item.linked_skill_id,
            my_role=rights.role,
            can_edit=rights.edit,
            can_publish=rights.publish,
            can_verify=rights.verify,
            can_change_access=rights.access,
            pending_change=pending,
        )

    async def _get(self, item_id: UUID) -> KnowledgeItem:
        item = await self.session.get(KnowledgeItem, item_id)
        if item is None:
            raise NotFoundError("We could not find that item.")
        return item

    async def _require(self, item: KnowledgeItem, user: User, right: str) -> Rights:
        rights = await self.policy.rights(item, user)
        if not getattr(rights, right):
            messages = {
                "edit": "Only the owner, backup owner or editors can change this item.",
                "publish": "Only the owner can publish changes.",
                "verify": "Only the owner or backup owner can confirm this item.",
                "access": "Only the owner and knowledge admins can change access.",
            }
            raise PermissionDeniedError(messages.get(right, "You cannot do that."))
        return rights

    # ---- adding (K-02) --------------------------------------------------------------------
    async def upload(self, filename: str, content: bytes, user: User) -> KnowledgeUpload:
        if len(content) > MAX_UPLOAD_BYTES:
            raise ValidationFailedError("The file is larger than 25 MB.")
        safe = Path(filename).name or "file"
        folder = Path(get_settings().upload_dir) / "knowledge"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{uuid.uuid4().hex}-{safe}"
        path.write_bytes(content)
        try:
            text = "\n".join(p.text for p in extract_pages(safe, content))
        except ValidationFailedError:
            text = ""  # images, spreadsheets: stored, just not searchable by text
        upload = KnowledgeUpload(
            filename=safe, path=str(path), size_bytes=len(content), text=text[:200_000], uploaded_by_id=user.id
        )
        self.session.add(upload)
        await self.session.flush()
        return upload

    async def download(self, item_id: UUID, upload_id: UUID, user: User) -> KnowledgeUpload:
        item, _ = await self.policy.get_readable(item_id, user)
        if not any(str(a.get("upload_id")) == str(upload_id) for a in item.attachments):
            raise NotFoundError("That file is not part of this item.")
        upload = await self.session.get(KnowledgeUpload, upload_id)
        if upload is None:
            raise NotFoundError("We could not find that file.")
        return upload

    async def suggest(self, data: SuggestIn, user: User) -> SuggestionOut:
        """The assistant suggests kind, category, owner, backup and review date. Nothing is saved."""
        title, text = data.title, data.text
        if data.upload_id:
            upload = await self.session.get(KnowledgeUpload, data.upload_id)
            if upload is None:
                raise NotFoundError("We could not find that upload.")
            title, text = title or upload.filename, text or upload.text
        if not title and data.link_url:
            title = data.link_url.rstrip("/").rsplit("/", 1)[-1]
        tree = await self.presenter.tree()
        paths = {tree.path(cid) or "": cid for cid in tree.by_id}
        suggestion = await get_assistant().suggest_knowledge(
            title=title or "New item", text=text, kinds=[k.value for k in ItemKind], categories=sorted(p for p in paths if p)
        )
        kind = ItemKind.LINK.value if data.link_url and not data.upload_id else suggestion.kind
        category_id = paths.get(suggestion.category_name or "") or await self._category_of_similar(f"{title} {text}", user)
        owner_id, backup_id = await self._likely_owners(category_id, user)
        names = await self.presenter.names({owner_id, backup_id})
        visibility, label = await self._default_visibility(category_id, tree)
        review_on = add_months(today(), suggestion.review_months) + timedelta(days=1)
        similar = await self._similar(suggestion.title, user)
        return SuggestionOut(
            title=suggestion.title,
            kind=kind,
            kind_label=KIND_LABELS.get(kind, kind),
            category_id=category_id,
            category_path=tree.path(category_id),
            owner_id=owner_id,
            owner_name=names.get(owner_id) if owner_id else None,
            backup_owner_id=backup_id,
            backup_owner_name=names.get(backup_id) if backup_id else None,
            review_on=review_on,
            review_label=f"In {suggestion.review_months} months: {review_on:%d %b %Y}",
            visibility=visibility,
            visibility_label=label,
            similar_item_id=similar.id if similar else None,
            similar_item_title=similar.title if similar else None,
            similar_item_version=similar.version_label if similar else None,
        )

    async def _likely_owners(self, category_id: UUID | None, user: User) -> tuple[UUID | None, UUID | None]:
        if category_id is None:
            return user.id, None
        category = await self.session.get(KnowledgeCategory, category_id)
        owners = Counter(
            (
                await self.session.scalars(
                    select(KnowledgeItem.owner_id).where(
                        KnowledgeItem.category_id == category_id, KnowledgeItem.owner_id.is_not(None)
                    )
                )
            ).all()
        )
        backups = Counter(
            (
                await self.session.scalars(
                    select(KnowledgeItem.backup_owner_id).where(
                        KnowledgeItem.category_id == category_id, KnowledgeItem.backup_owner_id.is_not(None)
                    )
                )
            ).all()
        )
        owner = owners.most_common(1)[0][0] if owners else (category.head_id if category and category.head_id else user.id)
        backup = next((b for b, _ in backups.most_common() if b != owner), None)
        return owner, backup

    async def _default_visibility(self, category_id: UUID | None, tree: Any) -> tuple[str, str]:
        root = tree.by_id.get(tree.root_of(category_id)) if category_id else None
        if root is not None:
            dept = (
                await self.session.scalars(select(Department).where(func.lower(Department.name) == root.name.lower()))
            ).first()
            if dept:
                return "team", f"{dept.name} team (Team)"
        return "company", "Everyone (Company)"

    async def _category_of_similar(self, text: str, user: User) -> UUID | None:
        """Fallback: put it where the most similar existing items live."""
        words = {w for w in re.findall(r"[a-z]{4,}", text.lower())}
        if not words:
            return None
        votes: Counter[UUID] = Counter()
        for item in (
            await self.session.scalars(
                select(KnowledgeItem).where(self.policy.readable_filter(user), KnowledgeItem.category_id.is_not(None))
            )
        ).all():
            overlap = len(words & set(re.findall(r"[a-z]{4,}", f"{item.title} {item.body[:3000]}".lower())))
            if overlap >= 2 and item.category_id:
                votes[item.category_id] += overlap
        return votes.most_common(1)[0][0] if votes else None

    async def _similar(self, title: str, user: User) -> KnowledgeItem | None:
        candidates = (
            await self.session.scalars(
                select(KnowledgeItem).where(self.policy.readable_filter(user), KnowledgeItem.status != ItemStatus.ARCHIVED.value)
            )
        ).all()
        best, best_ratio = None, 0.0
        for item in candidates:
            ratio = difflib.SequenceMatcher(None, title.lower(), item.title.lower()).ratio()
            if ratio > best_ratio:
                best, best_ratio = item, ratio
        return best if best_ratio >= 0.75 else None

    async def create(self, data: ItemIn, user: User) -> KnowledgeItem:
        if data.add_as_version_of:
            item = await self._get(data.add_as_version_of)
            body = data.body or await self._upload_text(data.upload_id)
            await self.update(item.id, ItemUpdate(title=None, body=body, change_note="New file uploaded", publish=True), user)
            await self._attach(item, data.upload_id)
            return item
        if data.kind not in {k.value for k in ItemKind}:
            raise ValidationFailedError("Choose a kind such as SOP, Policy or Checklist.")
        if data.visibility == Visibility.TEAM.value and not data.team_department_id:
            raise ValidationFailedError("Choose which team can see this item.")
        body = data.body or await self._upload_text(data.upload_id)
        item = KnowledgeItem(
            title=data.title.strip(),
            kind=data.kind,
            category_id=data.category_id,
            owner_id=data.owner_id or user.id,
            backup_owner_id=data.backup_owner_id,
            visibility=data.visibility,
            team_department_id=data.team_department_id,
            is_critical=data.is_critical,
            status=ItemStatus.PUBLISHED.value if data.publish else ItemStatus.DRAFT.value,
            body=body[:100_000],
            link_url=str(data.link_url) if data.link_url else None,
            review_months=data.review_months,
            next_review_on=add_months(today(), data.review_months) + timedelta(days=1),
            last_verified_at=utcnow() if data.publish else None,
            list_columns=data.list_columns,
            created_by_id=user.id,
        )
        self.session.add(item)
        await self.session.flush()
        await self._attach(item, data.upload_id)
        if data.publish:
            self.session.add(
                KnowledgeVersion(
                    item_id=item.id,
                    label="1.0",
                    title=item.title,
                    body=item.body,
                    change_note="First version",
                    is_major=True,
                    author_id=user.id,
                )
            )
        else:
            self.session.add(KnowledgeRevision(item_id=item.id, title=item.title, body=item.body, author_id=user.id))
        if item.owner_id and item.owner_id != user.id:
            await self.notify.notify(
                item.owner_id,
                kind=NotificationKind.KNOWLEDGE,
                title=f'You are now the owner of "{item.title}"',
                link=f"/knowledge/items/{item.id}",
                related=("knowledge_item", item.id),
            )
        self.audit.record("knowledge.created", "knowledge_item", item.id, actor_id=user.id, title=item.title)
        return item

    async def _upload_text(self, upload_id: UUID | None) -> str:
        if not upload_id:
            return ""
        upload = await self.session.get(KnowledgeUpload, upload_id)
        return upload.text if upload else ""

    async def _attach(self, item: KnowledgeItem, upload_id: UUID | None) -> None:
        if not upload_id:
            return
        upload = await self.session.get(KnowledgeUpload, upload_id)
        if upload is None:
            raise NotFoundError("We could not find that upload.")
        item.attachments = [*item.attachments, {"name": upload.filename, "upload_id": str(upload.id), "size": upload.size_bytes}]
        item.file_text = (item.file_text + "\n" + upload.text)[:200_000]

    # ---- changing -------------------------------------------------------------------------
    async def update(self, item_id: UUID, data: ItemUpdate, user: User) -> KnowledgeItem:
        item = await self._get(item_id)
        rights = await self._require(item, user, "edit")
        title = data.title or item.title
        body = data.body if data.body is not None else item.body
        if rights.publish and data.publish:
            await self._publish(item, title, body, data.change_note or "Updated", data.is_major, author=user, approver=None)
            return item
        status = "submitted" if data.publish else "draft"
        draft = (
            await self.session.scalars(
                select(KnowledgeRevision).where(
                    KnowledgeRevision.item_id == item.id,
                    KnowledgeRevision.author_id == user.id,
                    KnowledgeRevision.status == "draft",
                )
            )
        ).first()
        if draft and status == "draft":
            draft.title, draft.body, draft.note = title, body, data.change_note
        else:
            self.session.add(
                KnowledgeRevision(
                    item_id=item.id, title=title, body=body, note=data.change_note, status=status, author_id=user.id
                )
            )
        if status == "submitted" and item.owner_id:
            await self.notify.notify(
                item.owner_id,
                kind=NotificationKind.KNOWLEDGE,
                title=f"{item.title}: change by {user.full_name}",
                body="Waiting for your approval.",
                link="/knowledge/my-items",
                related=("knowledge_item", item.id),
            )
        await self.session.flush()
        return item

    async def _publish(
        self, item: KnowledgeItem, title: str, body: str, note: str, is_major: bool, *, author: User, approver: User | None
    ) -> KnowledgeVersion:
        if is_major:
            item.version_major, item.version_minor = item.version_major + 1, 0
        else:
            item.version_minor += 1
        item.title, item.body = title, body
        item.status = ItemStatus.PUBLISHED.value
        # An update counts as a review: the clock restarts and reminders stop.
        item.next_review_on = add_months(today(), item.review_months) + timedelta(days=1)
        item.last_verified_at = utcnow()
        item.snooze_count = 0
        version = KnowledgeVersion(
            item_id=item.id,
            label=item.version_label,
            title=title,
            body=body,
            change_note=note,
            is_major=is_major,
            author_id=author.id,
            approved_by_id=approver.id if approver else None,
        )
        self.session.add(version)
        self.session.add(KnowledgeReview(item_id=item.id, reviewer_id=(approver or author).id, outcome="updated", note=note))
        await self.session.flush()
        self.audit.record(
            "knowledge.published", "knowledge_item", item.id, actor_id=(approver or author).id, version=item.version_label
        )
        return version

    async def decide_revision(self, revision_id: UUID, approve: bool, user: User) -> KnowledgeItem:
        revision = await self.session.get(KnowledgeRevision, revision_id)
        if revision is None or revision.status != "submitted":
            raise NotFoundError("There is no change waiting here.")
        item = await self._get(revision.item_id)
        await self._require(item, user, "publish")
        author = await self.session.get(User, revision.author_id) if revision.author_id else None
        if approve:
            revision.status = "approved"
            await self._publish(
                item,
                revision.title,
                revision.body,
                revision.note or "Change approved",
                False,
                author=author or user,
                approver=user,
            )
        else:
            revision.status = "rejected"
        if author and author.id != user.id:
            await self.notify.notify(
                author.id,
                kind=NotificationKind.KNOWLEDGE,
                title=f'Your change to "{item.title}" was {"approved" if approve else "not accepted"}',
                link=f"/knowledge/items/{item.id}",
                related=("knowledge_item", item.id),
            )
        return item

    async def verify(self, item_id: UUID, user: User, note: str = "") -> KnowledgeItem:
        item = await self._get(item_id)
        await self._require(item, user, "verify")
        item.next_review_on = add_months(today(), item.review_months) + timedelta(days=1)
        item.last_verified_at = utcnow()
        item.snooze_count = 0
        if item.status == ItemStatus.IN_REVIEW.value:
            item.status = ItemStatus.PUBLISHED.value
        self.session.add(
            KnowledgeReview(
                item_id=item.id, reviewer_id=user.id, outcome="still_correct", note=note or "Still correct. No change."
            )
        )
        self.audit.record("knowledge.verified", "knowledge_item", item.id, actor_id=user.id)
        await self.session.flush()
        return item

    async def hand_over(self, item_id: UUID, new_owner_id: UUID, note: str, user: User) -> KnowledgeItem:
        item = await self._get(item_id)
        rights = await self.policy.rights(item, user)
        if not (rights.access or rights.role == "backup"):
            raise PermissionDeniedError("Only the owner, backup owner or a knowledge admin can hand this over.")
        new_owner = await self.session.get(User, new_owner_id)
        if new_owner is None or not new_owner.is_active:
            raise ValidationFailedError("Choose an active person as the new owner.")
        old = item.owner_id
        item.owner_id = new_owner.id
        if item.backup_owner_id == new_owner.id:
            item.backup_owner_id = old
        await self.notify.notify(
            new_owner.id,
            kind=NotificationKind.KNOWLEDGE,
            title=f'You are now the owner of "{item.title}"',
            body=note,
            link=f"/knowledge/items/{item.id}",
            related=("knowledge_item", item.id),
        )
        self.audit.record(
            "knowledge.handed_over", "knowledge_item", item.id, actor_id=user.id, old_owner=old, new_owner=new_owner.id
        )
        return item

    async def snooze(self, item_id: UUID, reason: str, user: User) -> KnowledgeItem:
        item = await self._get(item_id)
        await self._require(item, user, "verify")
        settings = SettingsService(self.session)
        max_snoozes = int(await settings.get("knowledge.max_snoozes"))
        if item.snooze_count >= max_snoozes:
            raise ConflictError("This item was already snoozed twice. Please confirm it, update it or hand it over.")
        item.snooze_count += 1
        days = int(await settings.get("knowledge.snooze_days"))
        item.next_review_on = max(item.next_review_on or today(), today()) + timedelta(days=days)
        self.session.add(KnowledgeReview(item_id=item.id, reviewer_id=user.id, outcome="snoozed", note=reason))
        if item.snooze_count >= max_snoozes:
            head_id = await self._function_head(item)
            if head_id:
                await self.notify.notify(
                    head_id,
                    kind=NotificationKind.KNOWLEDGE,
                    title=f'"{item.title}" was snoozed {item.snooze_count} times',
                    body=f"Reason: {reason}",
                    link=f"/knowledge/items/{item.id}",
                    related=("knowledge_item", item.id),
                )
        self.audit.record("knowledge.snoozed", "knowledge_item", item.id, actor_id=user.id, reason=reason)
        return item

    async def _function_head(self, item: KnowledgeItem) -> UUID | None:
        tree = await self.presenter.tree()
        root = tree.by_id.get(tree.root_of(item.category_id)) if item.category_id else None
        return root.head_id if root else None

    async def update_settings(self, item_id: UUID, data: ItemSettingsUpdate, user: User) -> KnowledgeItem:
        item = await self._get(item_id)
        await self._require(item, user, "publish")
        changes = data.model_dump(exclude_unset=True)
        if "kind" in changes and changes["kind"] not in {k.value for k in ItemKind}:
            raise ValidationFailedError("Unknown kind.")
        for key, value in changes.items():
            setattr(item, key, value)
        if "review_months" in changes and "next_review_on" not in changes and item.last_verified_at:
            item.next_review_on = add_months(item.last_verified_at.date(), item.review_months) + timedelta(days=1)
        self.audit.record("knowledge.settings_changed", "knowledge_item", item.id, actor_id=user.id, changes=list(changes))
        return item

    async def archive(self, item_id: UUID, user: User) -> KnowledgeItem:
        item = await self._get(item_id)
        await self._require(item, user, "publish")
        item.status = ItemStatus.ARCHIVED.value
        self.audit.record("knowledge.archived", "knowledge_item", item.id, actor_id=user.id)
        return item

    # ---- history (K-08) -------------------------------------------------------------------
    async def history(self, item_id: UUID, user: User) -> list[HistoryEntryOut]:
        item, _ = await self.policy.get_readable(item_id, user)
        versions = (await self.session.scalars(select(KnowledgeVersion).where(KnowledgeVersion.item_id == item.id))).all()
        revisions = (await self.session.scalars(select(KnowledgeRevision).where(KnowledgeRevision.item_id == item.id))).all()
        reviews = (
            await self.session.scalars(
                select(KnowledgeReview).where(KnowledgeReview.item_id == item.id, KnowledgeReview.outcome != "updated")
            )
        ).all()
        names = await self.presenter.names(
            {v.author_id for v in versions}
            | {v.approved_by_id for v in versions}
            | {r.author_id for r in revisions}
            | {r.reviewer_id for r in reviews}
        )
        entries = (
            [
                HistoryEntryOut(
                    kind="version",
                    id=v.id,
                    label=f"Version {v.label}",
                    summary=f"{v.change_note}{' (major)' if v.is_major and v.label != '1.0' else ''}",
                    by_name=names.get(v.author_id) if v.author_id else None,
                    approved_by_name=names.get(v.approved_by_id) if v.approved_by_id else None,
                    at=v.created_at,
                )
                for v in versions
            ]
            + [
                HistoryEntryOut(
                    kind="revision",
                    id=r.id,
                    label="Revision",
                    summary=r.note or ("Change sent for approval" if r.status == "submitted" else "Draft saved"),
                    by_name=names.get(r.author_id) if r.author_id else None,
                    approved_by_name=None,
                    at=r.updated_at,
                    status=r.status,
                )
                for r in revisions
            ]
            + [
                HistoryEntryOut(
                    kind="review",
                    id=r.id,
                    label="Review",
                    summary=r.note if r.outcome == "still_correct" else f"Snoozed: {r.note}",
                    by_name=names.get(r.reviewer_id) if r.reviewer_id else None,
                    approved_by_name=None,
                    at=r.created_at,
                )
                for r in reviews
            ]
        )
        return sorted(entries, key=lambda e: e.at, reverse=True)

    async def _version(self, item_id: UUID, label: str) -> KnowledgeVersion:
        version = (
            await self.session.scalars(
                select(KnowledgeVersion).where(KnowledgeVersion.item_id == item_id, KnowledgeVersion.label == label)
            )
        ).first()
        if version is None:
            raise NotFoundError(f"There is no version {label}.")
        return version

    async def compare(self, item_id: UUID, from_label: str, to_label: str, user: User) -> CompareOut:
        item, _ = await self.policy.get_readable(item_id, user)
        old, new = await self._version(item.id, from_label), await self._version(item.id, to_label)
        lines: list[DiffLineOut] = []
        for line in difflib.ndiff(old.body.splitlines(), new.body.splitlines()):
            if line.startswith("? "):
                continue
            op = {"+ ": "add", "- ": "remove"}.get(line[:2], "same")
            if line[2:].strip() or op != "same":
                lines.append(DiffLineOut(op=op, text=line[2:]))
        return CompareOut(from_label=old.label, to_label=new.label, lines=lines, change_note=new.change_note)

    async def restore(self, item_id: UUID, label: str, user: User) -> KnowledgeItem:
        item = await self._get(item_id)
        await self._require(item, user, "publish")
        version = await self._version(item.id, label)
        await self._publish(item, version.title, version.body, f"Restored version {label}", False, author=user, approver=None)
        return item

    async def turn_into_course(self, item_id: UUID, user: User) -> UUID:
        if not user.has_role("admin"):
            raise PermissionDeniedError("Only learning admins can create courses.")
        item, _ = await self.policy.get_readable(item_id, user)
        from app.modules.learning.course_service import CourseService
        from app.modules.learning.schemas import DraftOptions

        text = item.body or item.file_text
        if len(text.strip()) < 50:
            raise ValidationFailedError("This item has too little text to build a course from.")
        course = await CourseService(self.session).start_draft(
            f"{item.title}.txt", text.encode("utf-8"), DraftOptions(skill_id=item.linked_skill_id), user
        )
        course.knowledge_item_id = item.id
        item.linked_course_id = course.id
        return course.id

    async def can_manage(self, user: User) -> bool:
        return is_knowledge_admin(user)
