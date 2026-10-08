from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import Field, HttpUrl

from app.shared.schemas import Schema


class CategoryOut(Schema):
    id: UUID
    name: str
    parent_id: UUID | None
    head_id: UUID | None
    position: int
    item_count: int = 0
    path: str = ""


class CategoryIn(Schema):
    name: str = Field(min_length=1, max_length=120)
    parent_id: UUID | None = None
    head_id: UUID | None = None


class CategoryUpdate(Schema):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    parent_id: UUID | None = None
    head_id: UUID | None = None
    move_to_root: bool = False


class MergeIn(Schema):
    into_id: UUID


class ItemSummaryOut(Schema):
    id: UUID
    title: str
    kind: str
    kind_label: str
    category_id: UUID | None
    category_path: str | None
    owner_id: UUID | None
    owner_name: str | None
    version: str
    status: str  # draft | in_review | verified | due_soon | overdue | archived
    next_review_on: date | None
    is_critical: bool
    visibility: str
    updated_at: datetime


class ItemOut(ItemSummaryOut):
    body: str
    link_url: str | None
    attachments: list[dict[str, Any]]
    backup_owner_id: UUID | None
    backup_owner_name: str | None
    team_department_id: UUID | None
    review_months: int
    last_verified_at: datetime | None
    snooze_count: int
    version_count: int
    list_columns: list[str]
    linked_course_id: UUID | None
    linked_skill_id: UUID | None
    my_role: str
    can_edit: bool
    can_publish: bool
    can_verify: bool
    can_change_access: bool
    pending_change: bool


class ItemIn(Schema):
    title: str = Field(min_length=2, max_length=200)
    kind: str = "sop"
    category_id: UUID | None = None
    owner_id: UUID | None = None
    backup_owner_id: UUID | None = None
    visibility: str = Field(default="company", pattern="^(company|team|restricted)$")
    team_department_id: UUID | None = None
    is_critical: bool = False
    body: str = ""
    link_url: HttpUrl | None = None
    upload_id: UUID | None = None
    review_months: int = Field(default=12, ge=1, le=36)
    list_columns: list[str] = []
    publish: bool = True
    add_as_version_of: UUID | None = None  # "Similar item found: add as a new version instead?"


class ItemUpdate(Schema):
    """A change to the content. Owners publish it; editors send it to the owner."""

    title: str | None = Field(default=None, min_length=2, max_length=200)
    body: str | None = None
    change_note: str = Field(default="", max_length=500)
    is_major: bool = False
    publish: bool = True


class ItemSettingsUpdate(Schema):
    category_id: UUID | None = None
    kind: str | None = None
    visibility: str | None = Field(default=None, pattern="^(company|team|restricted)$")
    team_department_id: UUID | None = None
    is_critical: bool | None = None
    review_months: int | None = Field(default=None, ge=1, le=36)
    next_review_on: date | None = None
    backup_owner_id: UUID | None = None


class HandOverIn(Schema):
    new_owner_id: UUID
    note: str = Field(default="", max_length=300)


class SnoozeIn(Schema):
    reason: str = Field(min_length=3, max_length=300)


class SuggestionOut(Schema):
    title: str
    kind: str
    kind_label: str
    category_id: UUID | None
    category_path: str | None
    owner_id: UUID | None
    owner_name: str | None
    backup_owner_id: UUID | None
    backup_owner_name: str | None
    review_on: date
    review_label: str
    visibility: str
    visibility_label: str
    similar_item_id: UUID | None
    similar_item_title: str | None
    similar_item_version: str | None


class SuggestIn(Schema):
    title: str = ""
    text: str = ""
    upload_id: UUID | None = None
    link_url: str | None = None


class UploadOut(Schema):
    id: UUID
    filename: str
    size_bytes: int
    has_text: bool


class HistoryEntryOut(Schema):
    kind: str  # version | revision | review
    id: UUID
    label: str
    summary: str
    by_name: str | None
    approved_by_name: str | None
    at: datetime
    status: str | None = None


class DiffLineOut(Schema):
    op: str  # same | add | remove
    text: str


class CompareOut(Schema):
    from_label: str
    to_label: str
    lines: list[DiffLineOut]
    change_note: str


class AccessEntryOut(Schema):
    principal_type: str  # owner | backup | user | department
    principal_id: UUID | None
    name: str
    initials: str
    role: str
    rights: str


class AccessRequestOut(Schema):
    id: UUID
    item_id: UUID
    item_title: str
    requester_id: UUID
    requester_name: str
    role: str
    reason: str
    status: str
    created_at: datetime


class AccessOut(Schema):
    item_id: UUID
    item_title: str
    entries: list[AccessEntryOut]
    requests: list[AccessRequestOut]
    can_change: bool


class GrantIn(Schema):
    principal_type: str = Field(pattern="^(user|department)$")
    principal_id: UUID
    role: str = Field(default="viewer", pattern="^(viewer|editor)$")


class AccessRequestIn(Schema):
    role: str = Field(default="viewer", pattern="^(viewer|editor)$")
    reason: str = Field(default="", max_length=300)


class DecisionIn(Schema):
    approve: bool


class BulkIn(Schema):
    item_ids: list[UUID] = Field(min_length=1, max_length=500)
    action: str = Field(pattern="^(remind_owners|change_owner|set_review_date|change_category)$")
    owner_id: UUID | None = None
    review_on: date | None = None
    category_id: UUID | None = None


class SearchHitOut(Schema):
    item: ItemSummaryOut
    snippet: str
    score: float


class AnswerOut(Schema):
    answer: str
    sources: list[ItemSummaryOut]


class ListRowOut(Schema):
    id: UUID
    position: int
    data: dict[str, Any]
    updated_at: datetime


class ListRowIn(Schema):
    data: dict[str, Any]


class MyItemOut(Schema):
    item: ItemSummaryOut
    reason: str  # overdue | due_soon | waiting_for_me | draft
    detail: str
    revision_id: UUID | None = None
    can_snooze: bool = True


class MyItemsOut(Schema):
    overdue: int
    due_soon: int
    waiting_for_me: int
    drafts: int
    items: list[MyItemOut]
    coming_up: list[dict[str, str]]
    backup_note: str | None


class HealthTileOut(Schema):
    score: int
    items: int
    on_time_pct: int
    overdue: int
    due_soon: int
    no_owner: int
    no_backup: int
    critical: int


class FunctionHealthOut(Schema):
    category_id: UUID
    name: str
    score: int


class AttentionOut(Schema):
    text: str
    action: str
    href: str


class LeaderDashboardOut(Schema):
    company: HealthTileOut
    change_since_last_month: int | None
    functions_count: int
    trend: list[dict[str, Any]]
    by_function: list[FunctionHealthOut]
    attention: list[AttentionOut]
    target_on_time_pct: int


class CategoryHealthOut(Schema):
    category_id: UUID
    name: str
    items: int
    overdue: int
    ok_pct: int


class OwnerHealthOut(Schema):
    owner_id: UUID
    name: str
    items: int
    overdue: int


class FunctionDashboardOut(Schema):
    category_id: UUID
    name: str
    tile: HealthTileOut
    by_category: list[CategoryHealthOut]
    by_owner: list[OwnerHealthOut]
    overdue_owner_count: int
    items_without_backup: int


class HomeOut(Schema):
    types: list[dict[str, Any]]
    spaces: list[CategoryOut]
    recently_verified: list[ItemSummaryOut]
    critical: list[ItemSummaryOut]
    my_items: MyItemsOut
