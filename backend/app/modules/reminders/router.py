from fastapi import APIRouter

from app.core.deps import AdminUser, SessionDep
from app.modules.audit.service import AuditService
from app.modules.reminders.service import PlannedReminderOut, ReminderService
from app.modules.settings.service import SettingsService
from app.shared.schemas import Schema

router = APIRouter(prefix="/admin/reminders", tags=["reminders"])


class ReminderRulesOut(Schema):
    quiet_start: str
    quiet_end: str
    allow_weekends: bool
    max_per_day: int
    max_per_week: int
    paused: bool


class SentOut(Schema):
    created: int


@router.get("/rules", response_model=ReminderRulesOut)
async def reminder_rules(session: SessionDep, _: AdminUser) -> ReminderRulesOut:
    s = SettingsService(session)
    return ReminderRulesOut(
        quiet_start=await s.get("reminders.quiet_start"),
        quiet_end=await s.get("reminders.quiet_end"),
        allow_weekends=await s.get("reminders.allow_weekends"),
        max_per_day=await s.get("reminders.max_per_day"),
        max_per_week=await s.get("reminders.max_per_week"),
        paused=await s.get("workflows.automatic_sends_paused"),
    )


@router.get("/preview", response_model=list[PlannedReminderOut])
async def preview(session: SessionDep, _: AdminUser) -> object:
    return await ReminderService(session).preview()


@router.post("/send", response_model=SentOut)
async def send_now(session: SessionDep, admin: AdminUser) -> SentOut:
    """'Send reminders now' after the preview. A person pressed it, so it is not automatic."""
    created = await ReminderService(session).run(automatic=False)
    AuditService(session).record("reminders.sent_manually", "reminder", None, actor_id=admin.id, created=created)
    return SentOut(created=created)
