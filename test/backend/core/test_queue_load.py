"""Heavy load and retries: batching, idempotent job ids, Redis-down fallback + sweep, channel retries."""

from datetime import timedelta
from typing import Any

from sqlalchemy import func, select

from app.core.database import Database
from app.core.queue import BullMQQueue, InlineQueue, Job, Queues, dispatch_pending, set_queue
from app.modules.notifications.channels import CHANNELS, Rendered
from app.modules.notifications.jobs import redeliver
from app.modules.notifications.models import DeliveryLog, Notification
from app.modules.notifications.service import NotificationService
from app.shared import clock
from testkit import UserFactory


class RecordingQueue(InlineQueue):
    def __init__(self) -> None:
        super().__init__()
        self.batches: list[int] = []

    async def enqueue_many(self, jobs: list[Job]) -> None:
        self.batches.append(len(jobs))
        await super().enqueue_many(jobs)


class DownQueue:
    """Redis is unreachable."""

    async def enqueue(self, job: Job) -> None:
        raise ConnectionError("redis down")

    async def enqueue_many(self, jobs: list[Job]) -> None:
        raise ConnectionError("redis down")

    async def close(self) -> None:
        return None


def test_job_ids_make_repeats_harmless() -> None:
    opts = BullMQQueue._opts(Job(Queues.NOTIFICATIONS, "notifications.deliver", {"id": "abc", "attempt": 2}))
    assert opts["jobId"] == "notifications.deliver:abc:2" and opts["attempts"] == 5
    assert opts["backoff"] == {"type": "exponential", "delay": 5000}
    swept = BullMQQueue._opts(Job(Queues.NOTIFICATIONS, "notifications.deliver", {"id": "abc", "run": "202610051000"}))
    assert swept["jobId"] == "notifications.deliver:abc:1:202610051000"  # the sweep is never seen as a duplicate


async def test_many_messages_go_out_in_one_batch(database: Database, make_user: UserFactory) -> None:
    queue = RecordingQueue()
    set_queue(queue)
    users = [await make_user() for _ in range(30)]
    async with database.session_factory() as s:
        for user in users:
            await NotificationService(s).notify(user.id, kind="system", title="Hello")
        await s.commit()
        await dispatch_pending(s)
    assert queue.batches == [30]  # one call, not 30 round trips


async def test_redis_down_runs_a_few_inline_and_the_sweep_catches_the_rest(
    database: Database, make_user: UserFactory, monkeypatch: Any
) -> None:
    from app.core import config

    monkeypatch.setattr(config.get_settings(), "inline_fallback_limit", 5)
    users = [await make_user() for _ in range(12)]
    set_queue(DownQueue())  # type: ignore[arg-type]
    async with database.session_factory() as s:
        for user in users:
            await NotificationService(s).notify(user.id, kind="system", title="Hello")
        await s.commit()
        await dispatch_pending(s)  # never raises: the request still succeeds
    async with database.session_factory() as s:
        delivered = await s.scalar(select(func.count()).select_from(Notification).where(Notification.delivered_at.is_not(None)))
    assert delivered == 5  # only a few inline; the request stays fast

    set_queue(InlineQueue())  # Redis is back
    clock.freeze(clock.utcnow() + timedelta(minutes=15))
    async with database.session_factory() as s:
        assert await redeliver(s) == 7
        await s.commit()
        await dispatch_pending(s)
    async with database.session_factory() as s:
        left = await s.scalar(select(func.count()).select_from(Notification).where(Notification.delivered_at.is_(None)))
    assert left == 0  # nothing lost


async def test_failed_channel_is_retried_then_gives_up_and_in_app_is_logged_once(database: Database, make_user: UserFactory) -> None:
    user = await make_user(reminder_channels={"in_app": True, "email": True, "whatsapp": False})

    class FlakyEmail:
        key, label, simulated = "email", "Email", False
        calls = 0

        def render(self, u: Any, n: Any) -> Rendered:
            return Rendered(to=u.email, subject=n.title, text=n.body)

        async def send(self, *_: Any) -> str:
            FlakyEmail.calls += 1
            raise TimeoutError("smtp")

    original = CHANNELS["email"]
    CHANNELS["email"] = FlakyEmail()  # type: ignore[assignment]
    try:
        async with database.session_factory() as s:
            await NotificationService(s).notify(user.id, kind="system", title="Hello")
            await s.commit()
            await dispatch_pending(s)  # inline queue runs the retries straight away
    finally:
        CHANNELS["email"] = original
    async with database.session_factory() as s:
        logs = (await s.scalars(select(DeliveryLog).order_by(DeliveryLog.created_at))).all()
    email = [log for log in logs if log.channel == "email"]
    assert len([log for log in logs if log.channel == "in_app"]) == 1  # not repeated on retries
    assert 1 <= len(email) <= 4 and all(log.status in ("failed", "paused") for log in email)
    assert "Retry 2 in 5 s" in email[0].reason
    assert "No more retries" in email[-1].reason or email[-1].status == "paused"


async def test_delivering_twice_sends_nothing_new(database: Database, make_user: UserFactory) -> None:
    user = await make_user(reminder_channels={"in_app": True, "email": True, "whatsapp": False})
    async with database.session_factory() as s:
        note = await NotificationService(s).notify(user.id, kind="system", title="Hello")
        await s.commit()
        await dispatch_pending(s)
        assert note is not None
        await NotificationService(s).deliver(note.id)  # e.g. BullMQ retried after a crash
        await s.commit()
        count = await s.scalar(select(func.count()).select_from(DeliveryLog))
    assert count == 3  # in_app + email + whatsapp(skipped), once each
