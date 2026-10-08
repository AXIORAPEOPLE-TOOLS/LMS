"""Workflow engine (sheet 03, A-07): automatic, manual or both."""

import logging
from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError, ValidationFailedError
from app.modules.audit.service import AuditService
from app.modules.identity.models import User
from app.modules.notifications.models import NotificationKind
from app.modules.notifications.service import NotificationService
from app.modules.settings.service import SettingsService
from app.modules.workflows.actions import ACTIONS
from app.modules.workflows.models import RunStatus, Workflow, WorkflowMode, WorkflowRun
from app.shared.clock import utcnow

logger = logging.getLogger("workflows")


class WorkflowEngine:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.audit = AuditService(session)

    async def all_workflows(self) -> Sequence[Workflow]:
        return (await self.session.scalars(select(Workflow).order_by(Workflow.position))).all()

    async def get(self, workflow_id: UUID) -> Workflow:
        workflow = await self.session.get(Workflow, workflow_id)
        if workflow is None:
            raise NotFoundError("We could not find that workflow.")
        return workflow

    async def runs(self, *, status: str | None = None, limit: int = 50) -> Sequence[WorkflowRun]:
        stmt = select(WorkflowRun).order_by(WorkflowRun.created_at.desc()).limit(limit)
        if status:
            stmt = stmt.where(WorkflowRun.status == status)
        return (await self.session.scalars(stmt)).all()

    # ---- configuration ------------------------------------------------------------------
    async def set_mode(self, workflow_id: UUID, mode: str, actor: User) -> Workflow:
        if mode not in {m.value for m in WorkflowMode}:
            raise ValidationFailedError("Choose Manual, Hybrid or Auto.")
        workflow = await self.get(workflow_id)
        old = workflow.mode
        workflow.mode = mode
        self.audit.record("workflow.mode_changed", "workflow", workflow.id, actor_id=actor.id, old=old, new=mode)
        return workflow

    async def set_enabled(self, workflow_id: UUID, enabled: bool, actor: User) -> Workflow:
        workflow = await self.get(workflow_id)
        workflow.is_enabled = enabled
        self.audit.record("workflow.enabled" if enabled else "workflow.disabled", "workflow", workflow.id, actor_id=actor.id)
        return workflow

    async def set_paused(self, paused: bool, actor: User) -> None:
        await SettingsService(self.session).set("workflows.automatic_sends_paused", paused, actor.id)
        self.audit.record("workflow.stop_all" if paused else "workflow.resume_all", "workflow", None, actor_id=actor.id)

    # ---- running ------------------------------------------------------------------------
    async def preview(self, workflow: Workflow, context: dict[str, Any]) -> dict[str, Any]:
        lines: list[str] = []
        people = 0
        for code in workflow.actions:
            action = ACTIONS.get(code)
            if action is None:
                continue
            result = await action.preview(self.session, {**workflow.conditions, **context})
            lines.extend(result.get("lines", []))
            people = max(people, int(result.get("people", 0)))
        return {"lines": lines, "people": people}

    async def _execute(self, workflow: Workflow, run: WorkflowRun, actor: User | None) -> None:
        lines: list[str] = []
        try:
            async with self.session.begin_nested():  # all actions or none
                for code in workflow.actions:
                    action = ACTIONS.get(code)
                    if action is None:
                        continue
                    result = await action.execute(self.session, {**workflow.conditions, **run.context}, actor)
                    lines.extend(result.get("lines", []))
            run.status = RunStatus.COMPLETED.value
            run.result = {"lines": lines}
        except Exception as exc:
            logger.exception("Workflow %s failed", workflow.code)
            run.status = RunStatus.FAILED.value
            run.result = {"error": "This run could not finish. Nothing was sent.", "detail": type(exc).__name__}

    async def on_trigger(self, trigger: str, context: dict[str, Any], *, triggered_by: str = "event") -> list[WorkflowRun]:
        """Called by events and the scheduler. Mode decides what happens."""
        paused = await SettingsService(self.session).get("workflows.automatic_sends_paused")
        workflows = (
            await self.session.scalars(select(Workflow).where(Workflow.trigger == trigger, Workflow.is_enabled.is_(True)))
        ).all()
        runs: list[WorkflowRun] = []
        for workflow in workflows:
            if workflow.mode == WorkflowMode.MANUAL.value:
                continue  # people run it by hand
            if workflow.mode == WorkflowMode.AUTO.value and not paused:
                run = WorkflowRun(
                    workflow_id=workflow.id,
                    triggered_by=triggered_by,
                    status=RunStatus.PENDING_APPROVAL.value,
                    context=context,
                    preview=await self.preview(workflow, context),
                )
                self.session.add(run)
                await self.session.flush()
                await self._execute(workflow, run, None)
            else:
                # Hybrid (or auto while paused): prepare a batch and ask a person.
                run = await self._add_to_pending_batch(workflow, context, triggered_by)
            runs.append(run)
        return runs

    async def _add_to_pending_batch(self, workflow: Workflow, context: dict[str, Any], triggered_by: str) -> WorkflowRun:
        pending = (
            await self.session.scalars(
                select(WorkflowRun).where(
                    WorkflowRun.workflow_id == workflow.id, WorkflowRun.status == RunStatus.PENDING_APPROVAL.value
                )
            )
        ).first()
        if pending and context.get("user_ids") and pending.context.get("user_ids") is not None:
            ids = list(dict.fromkeys([*pending.context["user_ids"], *[str(u) for u in context["user_ids"]]]))
            pending.context = {**pending.context, "user_ids": ids}
            pending.preview = await self.preview(workflow, pending.context)
            return pending
        if pending and not context:
            pending.preview = await self.preview(workflow, pending.context)
            return pending
        stored = {
            k: ([str(x) for x in v] if isinstance(v, list) else str(v) if isinstance(v, UUID) else v) for k, v in context.items()
        }
        run = WorkflowRun(
            workflow_id=workflow.id,
            triggered_by=triggered_by,
            status=RunStatus.PENDING_APPROVAL.value,
            context=stored,
            preview=await self.preview(workflow, stored),
        )
        self.session.add(run)
        await self.session.flush()
        await self._tell_admins(workflow)
        return run

    async def _tell_admins(self, workflow: Workflow) -> None:
        admins = (await self.session.scalars(select(User).where(User.is_active.is_(True)))).all()
        for admin in admins:
            if admin.has_role("admin"):
                await NotificationService(self.session).notify(
                    admin.id,
                    kind=NotificationKind.APPROVAL,
                    title=f'"{workflow.name}" is ready for your check',
                    body="Look at the preview and approve to send.",
                    link="/admin/workflows",
                )

    async def run_now(self, workflow_id: UUID, context: dict[str, Any], actor: User) -> WorkflowRun:
        """Run by hand (every workflow can be). The caller has already seen the preview."""
        workflow = await self.get(workflow_id)
        run = WorkflowRun(
            workflow_id=workflow.id,
            triggered_by="manual",
            status=RunStatus.PENDING_APPROVAL.value,
            context=context,
            preview=await self.preview(workflow, context),
            decided_by_id=actor.id,
            decided_at=utcnow(),
        )
        self.session.add(run)
        await self.session.flush()
        await self._execute(workflow, run, actor)
        self.audit.record("workflow.run_manually", "workflow", workflow.id, actor_id=actor.id, status=run.status)
        return run

    async def decide(self, run_id: UUID, approve: bool, actor: User) -> WorkflowRun:
        run = await self.session.get(WorkflowRun, run_id)
        if run is None:
            raise NotFoundError("We could not find that run.")
        if run.status != RunStatus.PENDING_APPROVAL.value:
            raise ConflictError("This run was already decided.")
        workflow = await self.get(run.workflow_id)
        run.decided_by_id, run.decided_at = actor.id, utcnow()
        if approve:
            await self._execute(workflow, run, actor)
        else:
            run.status = RunStatus.CANCELLED.value
        self.audit.record(
            "workflow.run_approved" if approve else "workflow.run_cancelled", "workflow_run", run.id, actor_id=actor.id
        )
        return run
