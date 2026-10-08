from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter
from pydantic import Field

from app.core.deps import AdminUser, SessionDep
from app.modules.settings.service import SettingsService
from app.modules.workflows.actions import ACTIONS
from app.modules.workflows.service import WorkflowEngine
from app.shared.schemas import Schema

router = APIRouter(prefix="/admin/workflows", tags=["workflows"])


class WorkflowOut(Schema):
    id: UUID
    code: str
    name: str
    description: str
    trigger: str
    trigger_label: str
    condition_label: str
    actions: list[str]
    action_labels: list[str] = []
    approval_label: str
    mode: str
    is_enabled: bool


class WorkflowsOut(Schema):
    paused: bool
    workflows: list[WorkflowOut]
    pending_runs: int


class RunOut(Schema):
    id: UUID
    workflow_id: UUID
    triggered_by: str
    status: str
    context: dict[str, Any]
    preview: dict[str, Any]
    result: dict[str, Any]
    created_at: datetime
    decided_at: datetime | None


class ModeIn(Schema):
    mode: str = Field(pattern="^(manual|hybrid|auto)$")


class EnabledIn(Schema):
    enabled: bool


class PauseIn(Schema):
    paused: bool


class ContextIn(Schema):
    context: dict[str, Any] = {}


class DecisionIn(Schema):
    approve: bool


def _out(workflow: Any) -> WorkflowOut:
    out = WorkflowOut.model_validate(workflow)
    out.action_labels = [ACTIONS[c].label for c in workflow.actions if c in ACTIONS]
    return out


@router.get("", response_model=WorkflowsOut)
async def list_workflows(session: SessionDep, _: AdminUser) -> WorkflowsOut:
    engine = WorkflowEngine(session)
    return WorkflowsOut(
        paused=await SettingsService(session).get("workflows.automatic_sends_paused"),
        workflows=[_out(w) for w in await engine.all_workflows()],
        pending_runs=len(await engine.runs(status="pending_approval")),
    )


@router.put("/{workflow_id}/mode", response_model=WorkflowOut)
async def set_mode(workflow_id: UUID, data: ModeIn, session: SessionDep, admin: AdminUser) -> WorkflowOut:
    return _out(await WorkflowEngine(session).set_mode(workflow_id, data.mode, admin))


@router.put("/{workflow_id}/enabled", response_model=WorkflowOut)
async def set_enabled(workflow_id: UUID, data: EnabledIn, session: SessionDep, admin: AdminUser) -> WorkflowOut:
    return _out(await WorkflowEngine(session).set_enabled(workflow_id, data.enabled, admin))


@router.put("/pause", status_code=204)
async def pause_all(data: PauseIn, session: SessionDep, admin: AdminUser) -> None:
    """'Stop all automatic sends' — and back on again."""
    await WorkflowEngine(session).set_paused(data.paused, admin)


@router.post("/{workflow_id}/preview")
async def preview(workflow_id: UUID, data: ContextIn, session: SessionDep, _: AdminUser) -> dict[str, Any]:
    engine = WorkflowEngine(session)
    return await engine.preview(await engine.get(workflow_id), data.context)


@router.post("/{workflow_id}/run", response_model=RunOut)
async def run_now(workflow_id: UUID, data: ContextIn, session: SessionDep, admin: AdminUser) -> object:
    return await WorkflowEngine(session).run_now(workflow_id, data.context, admin)


@router.get("/runs", response_model=list[RunOut])
async def runs(session: SessionDep, _: AdminUser, status: str | None = None) -> object:
    return await WorkflowEngine(session).runs(status=status)


@router.post("/runs/{run_id}/decision", response_model=RunOut)
async def decide(run_id: UUID, data: DecisionIn, session: SessionDep, admin: AdminUser) -> object:
    return await WorkflowEngine(session).decide(run_id, data.approve, admin)
