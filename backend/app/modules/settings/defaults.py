"""Every business default from the build spec, in one place.

Values here are only the starting point: admins override them through the
`app_settings` table (golden rule 8: settings, not hard-coded numbers).
"""

from typing import Any

DEFAULTS: dict[str, tuple[Any, str]] = {
    # Skills (sheet 04)
    "skills.level_bands": (
        [[0, 0], [20, 1], [40, 2], [60, 3], [75, 4], [90, 5]],
        "Minimum test score (0-100) for each level 0-5.",
    ),
    "skills.level_names": (
        ["None", "Awareness", "Working", "Proficient", "Advanced", "Expert"],
        "Plain name for each level 0-5.",
    ),
    "skills.role_ready_level": (3, "Level that counts as role-ready for most roles."),
    # Pathways
    "pathways.wave_size": (3, "Skills per pathway wave."),
    "pathways.hours_per_level": (1.8, "Learning hours needed to close one level of gap."),
    "pathways.default_hours_per_week": (3, "Default weekly learning time."),
    "pathways.require_manager_approval": (True, "Manager approves a pathway before it starts."),
    # Reminders (sheet 12)
    "reminders.quiet_start": ("09:00", "No messages before this time."),
    "reminders.quiet_end": ("19:00", "No messages after this time."),
    "reminders.allow_weekends": (False, "Send reminders on Saturday and Sunday."),
    "reminders.max_per_day": (1, "Most reminders one person gets in a day."),
    "reminders.max_per_week": (3, "Most reminders one person gets in a week."),
    "reminders.default_window": (["11:00", "13:00"], "Default best time window."),
    "reminders.holidays": ([], "Dates (YYYY-MM-DD) with no messages."),
    "safety.undo_minutes": (10, "Minutes during which a bulk send can be undone."),
    "workflows.automatic_sends_paused": (False, "Stop all automatic sends."),
    # Assessment and proctoring (sheet 09)
    "proctoring.snapshot_seconds": (45, "Seconds between camera snapshots."),
    "proctoring.retention_days": (30, "Days to keep proctoring pictures after a case closes."),
    "certificates.validity_months": (12, "How long a certificate stays valid."),
    "certificates.renewal_reminder_days": ([60, 30, 7], "Days before expiry to remind."),
    # Gamification (sheet 11)
    "gamification.points": (
        {"lesson": 10, "course": 30, "test": 20, "level_up": 50, "certificate": 40, "challenge": 50},
        "Points per action. Points are only for real learning.",
    ),
    "gamification.levels": (
        [[0, "Starter"], [500, "Learner"], [1000, "Practitioner"], [1500, "Specialist"], [2500, "Expert"]],
        "Points needed for each profile level.",
    ),
    # Knowledge Hub (sheet 14)
    "knowledge.review_months": (12, "Default months between reviews."),
    "knowledge.due_soon_days": (30, "Items due within this many days show as due soon."),
    "knowledge.snooze_days": (7, "Days one snooze adds."),
    "knowledge.max_snoozes": (2, "Snoozes allowed before the function head is told."),
    "knowledge.ai_exclusion_overdue_days": (30, "Overdue items are left out of answers after this."),
    "knowledge.health_weights": (
        {"on_time": 0.7, "owner": 0.15, "backup": 0.15},
        "Weights for the knowledge health score (sum to 1).",
    ),
}
