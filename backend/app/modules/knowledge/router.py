"""Knowledge Hub API. Its own prefix, its own permissions: /api/knowledge/..."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, UploadFile
from fastapi.responses import FileResponse

from app.core.deps import CurrentUser, SessionDep, require_roles
from app.modules.identity.models import User
from app.modules.knowledge import reports as _knowledge_reports  # noqa: F401  (registers reports)
from app.modules.knowledge.access_service import AccessService
from app.modules.knowledge.catalog_service import CategoryService, ListService
from app.modules.knowledge.dashboard_service import DashboardService
from app.modules.knowledge.item_service import MAX_UPLOAD_BYTES, ItemService
from app.modules.knowledge.library_service import LibraryService
from app.modules.knowledge.schemas import (
    AccessOut,
    AccessRequestIn,
    AccessRequestOut,
    AnswerOut,
    BulkIn,
    CategoryIn,
    CategoryOut,
    CategoryUpdate,
    CompareOut,
    DecisionIn,
    FunctionDashboardOut,
    GrantIn,
    HandOverIn,
    HistoryEntryOut,
    HomeOut,
    ItemIn,
    ItemOut,
    ItemSettingsUpdate,
    ItemSummaryOut,
    ItemUpdate,
    LeaderDashboardOut,
    ListRowIn,
    ListRowOut,
    MergeIn,
    MyItemsOut,
    SearchHitOut,
    SnoozeIn,
    SuggestIn,
    SuggestionOut,
    UploadOut,
)
from app.shared.schemas import Schema

router = APIRouter(prefix="/knowledge", tags=["knowledge"])
LeaderUser = Annotated[User, Depends(require_roles("knowledge_admin", "admin", "function_head", "manager"))]


class QuestionIn(Schema):
    question: str


class OwnerIn(Schema):
    owner_id: UUID


class CountOut(Schema):
    count: int


class VerifyIn(Schema):
    note: str = ""


# ---- find ------------------------------------------------------------------------------
@router.get("/home", response_model=HomeOut)
async def home(session: SessionDep, user: CurrentUser) -> object:
    return await LibraryService(session).home(user)


@router.get("/library")
async def library(
    session: SessionDep,
    user: CurrentUser,
    category_id: UUID | None = None,
    kind: str | None = None,
    status: str | None = None,
    owner_id: UUID | None = None,
    critical: bool | None = None,
    q: str | None = None,
    sort: str = "title",
) -> dict[str, Any]:
    return await LibraryService(session).library(
        user, category_id=category_id, kind=kind, status=status, owner_id=owner_id, critical=critical, q=q, sort=sort
    )


@router.get("/search", response_model=list[SearchHitOut])
async def search(q: str, session: SessionDep, user: CurrentUser) -> object:
    return await LibraryService(session).search(user, q)


@router.post("/ask", response_model=AnswerOut)
async def ask(data: QuestionIn, session: SessionDep, user: CurrentUser) -> object:
    return await LibraryService(session).ask(user, data.question)


@router.get("/my-items", response_model=MyItemsOut)
async def my_items(session: SessionDep, user: CurrentUser) -> object:
    return await LibraryService(session).my_items(user)


@router.post("/bulk", response_model=CountOut)
async def bulk(data: BulkIn, session: SessionDep, user: CurrentUser) -> CountOut:
    return CountOut(count=await LibraryService(session).bulk(user, data))


# ---- add (three clicks) ----------------------------------------------------------------
@router.post("/uploads", response_model=UploadOut, status_code=201)
async def upload(file: UploadFile, session: SessionDep, user: CurrentUser) -> UploadOut:
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    saved = await ItemService(session).upload(file.filename or "file", content, user)
    return UploadOut(id=saved.id, filename=saved.filename, size_bytes=saved.size_bytes, has_text=bool(saved.text.strip()))


@router.post("/suggest", response_model=SuggestionOut)
async def suggest(data: SuggestIn, session: SessionDep, user: CurrentUser) -> object:
    return await ItemService(session).suggest(data, user)


@router.post("/items", response_model=ItemOut, status_code=201)
async def create_item(data: ItemIn, session: SessionDep, user: CurrentUser) -> object:
    service = ItemService(session)
    item = await service.create(data, user)
    return await service.detail(item.id, user)


# ---- one item ------------------------------------------------------------------------------
@router.get("/items/{item_id}", response_model=ItemOut)
async def item_detail(item_id: UUID, session: SessionDep, user: CurrentUser) -> object:
    return await ItemService(session).detail(item_id, user)


@router.put("/items/{item_id}", response_model=ItemOut)
async def update_item(item_id: UUID, data: ItemUpdate, session: SessionDep, user: CurrentUser) -> object:
    service = ItemService(session)
    await service.update(item_id, data, user)
    return await service.detail(item_id, user)


@router.patch("/items/{item_id}/settings", response_model=ItemOut)
async def update_settings(item_id: UUID, data: ItemSettingsUpdate, session: SessionDep, user: CurrentUser) -> object:
    service = ItemService(session)
    await service.update_settings(item_id, data, user)
    return await service.detail(item_id, user)


@router.post("/items/{item_id}/verify", response_model=ItemOut)
async def verify(item_id: UUID, data: VerifyIn, session: SessionDep, user: CurrentUser) -> object:
    service = ItemService(session)
    await service.verify(item_id, user, data.note)
    return await service.detail(item_id, user)


@router.post("/items/{item_id}/hand-over", response_model=ItemOut)
async def hand_over(item_id: UUID, data: HandOverIn, session: SessionDep, user: CurrentUser) -> object:
    service = ItemService(session)
    await service.hand_over(item_id, data.new_owner_id, data.note, user)
    return await service.detail(item_id, user)


@router.post("/items/{item_id}/snooze", response_model=ItemOut)
async def snooze(item_id: UUID, data: SnoozeIn, session: SessionDep, user: CurrentUser) -> object:
    service = ItemService(session)
    await service.snooze(item_id, data.reason, user)
    return await service.detail(item_id, user)


@router.post("/items/{item_id}/archive", status_code=204)
async def archive(item_id: UUID, session: SessionDep, user: CurrentUser) -> None:
    await ItemService(session).archive(item_id, user)


@router.get("/items/{item_id}/history", response_model=list[HistoryEntryOut])
async def history(item_id: UUID, session: SessionDep, user: CurrentUser) -> object:
    return await ItemService(session).history(item_id, user)


@router.get("/items/{item_id}/compare", response_model=CompareOut)
async def compare(item_id: UUID, from_version: str, to_version: str, session: SessionDep, user: CurrentUser) -> object:
    return await ItemService(session).compare(item_id, from_version, to_version, user)


@router.post("/items/{item_id}/restore/{label}", response_model=ItemOut)
async def restore(item_id: UUID, label: str, session: SessionDep, user: CurrentUser) -> object:
    service = ItemService(session)
    await service.restore(item_id, label, user)
    return await service.detail(item_id, user)


@router.post("/revisions/{revision_id}/decision", status_code=204)
async def decide_revision(revision_id: UUID, data: DecisionIn, session: SessionDep, user: CurrentUser) -> None:
    await ItemService(session).decide_revision(revision_id, data.approve, user)


@router.get("/items/{item_id}/files/{upload_id}")
async def download(item_id: UUID, upload_id: UUID, session: SessionDep, user: CurrentUser) -> FileResponse:
    upload = await ItemService(session).download(item_id, upload_id, user)
    return FileResponse(upload.path, filename=upload.filename)


@router.post("/items/{item_id}/course")
async def turn_into_course(item_id: UUID, session: SessionDep, user: CurrentUser) -> dict[str, UUID]:
    return {"course_id": await ItemService(session).turn_into_course(item_id, user)}


# ---- access & owners (K-05) ------------------------------------------------------------------
@router.get("/items/{item_id}/access", response_model=AccessOut)
async def access(item_id: UUID, session: SessionDep, user: CurrentUser) -> object:
    return await AccessService(session).view(item_id, user)


@router.post("/items/{item_id}/access", status_code=204)
async def grant(item_id: UUID, data: GrantIn, session: SessionDep, user: CurrentUser) -> None:
    await AccessService(session).grant(item_id, data, user)


@router.delete("/items/{item_id}/access/{principal_type}/{principal_id}", status_code=204)
async def revoke(item_id: UUID, principal_type: str, principal_id: UUID, session: SessionDep, user: CurrentUser) -> None:
    await AccessService(session).revoke(item_id, principal_type, principal_id, user)


@router.post("/items/{item_id}/access-requests", response_model=AccessRequestOut, status_code=201)
async def request_access(item_id: UUID, data: AccessRequestIn, session: SessionDep, user: CurrentUser) -> AccessRequestOut:
    service = AccessService(session)
    created = await service.request(item_id, user, data.role, data.reason)
    return next(r for r in await service.requests(item_ids=[created.item_id]) if r.id == created.id)


@router.get("/access-requests", response_model=list[AccessRequestOut])
async def access_requests(session: SessionDep, user: CurrentUser) -> object:
    return await AccessService(session).requests(owner=user)


@router.post("/access-requests/{request_id}/decision", status_code=204)
async def decide_access(request_id: UUID, data: DecisionIn, session: SessionDep, user: CurrentUser) -> None:
    await AccessService(session).decide(request_id, data.approve, user)


@router.get("/without-owner", response_model=list[ItemSummaryOut])
async def without_owner(session: SessionDep, user: CurrentUser) -> object:
    return await AccessService(session).without_owner(user)


@router.post("/items/{item_id}/owner", status_code=204)
async def assign_owner(item_id: UUID, data: OwnerIn, session: SessionDep, user: CurrentUser) -> None:
    await AccessService(session).assign_owner(item_id, data.owner_id, user)


# ---- categories & lists ------------------------------------------------------------------------
@router.post("/categories", response_model=CategoryOut, status_code=201)
async def create_category(data: CategoryIn, session: SessionDep, user: CurrentUser) -> object:
    return await CategoryService(session).create(data, user)


@router.patch("/categories/{category_id}", response_model=CategoryOut)
async def update_category(category_id: UUID, data: CategoryUpdate, session: SessionDep, user: CurrentUser) -> object:
    return await CategoryService(session).update(category_id, data, user)


@router.post("/categories/{category_id}/merge", response_model=CountOut)
async def merge_category(category_id: UUID, data: MergeIn, session: SessionDep, user: CurrentUser) -> CountOut:
    return CountOut(count=await CategoryService(session).merge(category_id, data.into_id, user))


@router.delete("/categories/{category_id}", status_code=204)
async def delete_category(category_id: UUID, session: SessionDep, user: CurrentUser) -> None:
    await CategoryService(session).delete(category_id, user)


@router.get("/items/{item_id}/rows")
async def list_rows(
    item_id: UUID, session: SessionDep, user: CurrentUser, status: str | None = None, owner: str | None = None
) -> dict[str, Any]:
    filters = {k.title(): v for k, v in {"status": status, "owner": owner}.items() if v}
    columns, rows = await ListService(session).rows(item_id, user, filters)
    return {"columns": columns, "rows": [ListRowOut.model_validate(r) for r in rows]}


@router.post("/items/{item_id}/rows", response_model=ListRowOut, status_code=201)
async def add_row(item_id: UUID, data: ListRowIn, session: SessionDep, user: CurrentUser) -> object:
    return await ListService(session).add_row(item_id, data.data, user)


@router.patch("/items/{item_id}/rows/{row_id}", response_model=ListRowOut)
async def update_row(item_id: UUID, row_id: UUID, data: ListRowIn, session: SessionDep, user: CurrentUser) -> object:
    return await ListService(session).update_row(item_id, row_id, data.data, user)


@router.delete("/items/{item_id}/rows/{row_id}", status_code=204)
async def delete_row(item_id: UUID, row_id: UUID, session: SessionDep, user: CurrentUser) -> None:
    await ListService(session).delete_row(item_id, row_id, user)


@router.post("/items/{item_id}/rows/import", response_model=CountOut)
async def import_rows(item_id: UUID, file: UploadFile, session: SessionDep, user: CurrentUser) -> CountOut:
    content = await file.read(5 * 1024 * 1024)
    return CountOut(count=await ListService(session).import_file(item_id, file.filename or "list.csv", content, user))


# ---- dashboards ------------------------------------------------------------------------------------
@router.get("/dashboard", response_model=LeaderDashboardOut)
async def leader_dashboard(session: SessionDep, _: LeaderUser) -> object:
    return await DashboardService(session).leader()


@router.get("/dashboard/{category_id}", response_model=FunctionDashboardOut)
async def function_dashboard(category_id: UUID, session: SessionDep, _: LeaderUser) -> object:
    return await DashboardService(session).function(category_id)
