"""The ready-made workflows from sheet 03 / slide 18. Upserted by code, so admin choices survive."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.workflows.models import Workflow

DEFAULT_WORKFLOWS: list[dict[str, Any]] = [
    {
        "code": "new_joiner",
        "name": "New joiner",
        "trigger": "user.created",
        "trigger_label": "A new person is added",
        "actions": ["assign_mandatory_training", "create_skill_tests", "send_welcome"],
        "approval_label": "L&D admin approves the first batch",
        "mode": "hybrid",
    },
    {
        "code": "skill_test_campaign",
        "name": "Skill test campaign",
        "trigger": "user.role_changed",
        "trigger_label": "A person changes role",
        "actions": ["create_skill_tests"],
        "approval_label": "L&D admin approves",
        "mode": "hybrid",
    },
    {
        "code": "completion_reminders",
        "name": "Completion reminders",
        "trigger": "schedule:daily",
        "trigger_label": "Every weekday, in each person's best time",
        "actions": ["send_completion_reminders"],
        "approval_label": "No approval needed",
        "mode": "auto",
    },
    {
        "code": "mandatory_training",
        "name": "Mandatory training (POSH, DPDP)",
        "trigger": "schedule:weekly",
        "trigger_label": "Every Monday",
        "actions": ["assign_mandatory_training"],
        "approval_label": "L&D admin approves",
        "mode": "hybrid",
    },
    {
        "code": "certificate_renewal",
        "name": "Certificate renewal",
        "trigger": "schedule:daily",
        "trigger_label": "60, 30 and 7 days before expiry",
        "actions": ["certificate_renewal_reminders"],
        "approval_label": "No approval needed",
        "mode": "auto",
    },
    {
        "code": "session_invitations",
        "name": "Session invitations",
        "trigger": "session.created",
        "trigger_label": "A session is scheduled",
        "actions": ["send_session_invitations"],
        "approval_label": "The organiser checks the preview",
        "mode": "hybrid",
    },
    {
        "code": "weekly_overdue_summary",
        "name": "Weekly overdue summary",
        "trigger": "schedule:weekly",
        "trigger_label": "Every Monday",
        "actions": ["weekly_overdue_summary"],
        "approval_label": "No approval needed",
        "mode": "auto",
    },
]


async def ensure_default_workflows(session: AsyncSession) -> int:
    existing = set((await session.scalars(select(Workflow.code))).all())
    created = 0
    for position, data in enumerate(DEFAULT_WORKFLOWS):
        if data["code"] in existing:
            continue
        session.add(Workflow(position=position, **data))
        created += 1
    await session.flush()
    return created
