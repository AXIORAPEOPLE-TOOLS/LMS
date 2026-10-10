"""Step lists for each helper and a small log that keeps every step's status and detail on the run."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.agents.models import AgentRun, RunKind
from app.shared.clock import utcnow

COURSE_STEPS = [
    ("brief", "Read the brief"),
    ("material", "Look for company material"),
    ("outline", "Plan the modules and what learners will be able to do"),
    ("content", "Write each module with an example"),
    ("resources", "Add links and documents"),
    ("quiz", "Write the quick check"),
    ("check", "Check the draft"),
    ("trial", "Try it as a learner"),
    ("expert", "Subject expert checks and approves"),
]

QUIZ_STEPS = [
    ("content", "Read the course content and goals"),
    ("draft", "Draft questions with answers"),
    ("settings", "Set the pass mark and time limit"),
    ("check", "Check accuracy and difficulty"),
    ("save", "Save to the course"),
    ("trial", "Try it once"),
    ("review", "Subject expert checks the questions"),
]

ASSIGN_STEPS = [
    ("read", "Read the request"),
    ("due", "Set the due date"),
    ("who", "Check who gets it"),
    ("confirm", "Wait for your go-ahead"),
    ("assign", "Assign and send the notice"),
    ("visible", "Confirm it shows for each person"),
    ("tracker", "Record it in the tracker"),
]

STEPS_BY_KIND = {RunKind.COURSE.value: COURSE_STEPS, RunKind.QUIZ.value: QUIZ_STEPS, RunKind.ASSIGN.value: ASSIGN_STEPS}


def initial_steps(kind: str) -> list[dict[str, object]]:
    return [{"key": k, "label": label, "status": "pending", "detail": "", "at": None} for k, label in STEPS_BY_KIND[kind]]


class StepLog:
    """Updates one step at a time. With `live=True` (worker) each change is committed so the page shows progress."""

    def __init__(self, session: AsyncSession, run: AgentRun, *, live: bool = False) -> None:
        self.session = session
        self.run = run
        self.live = live

    async def _set(self, key: str, status: str, detail: str = "") -> None:
        steps = [dict(s) for s in self.run.steps]
        for step in steps:
            if step["key"] == key:
                step.update(status=status, detail=detail[:1000], at=utcnow().isoformat())
        self.run.steps = steps  # new list so the JSON column is saved
        if self.live:
            await self.session.commit()

    async def start(self, key: str) -> None:
        await self._set(key, "running")

    async def done(self, key: str, detail: str) -> None:
        await self._set(key, "done", detail)

    async def skip(self, key: str, detail: str) -> None:
        await self._set(key, "skipped", detail)

    async def wait(self, key: str, detail: str) -> None:
        await self._set(key, "waiting", detail)

    async def fail_running(self, detail: str) -> None:
        running = next((s["key"] for s in self.run.steps if s["status"] == "running"), None)
        if running:
            await self._set(running, "failed", detail)
