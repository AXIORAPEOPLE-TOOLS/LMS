from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Database
from app.core.queue import InlineQueue, dispatch_pending
from app.modules.notifications.models import Notification
from app.modules.notifications.service import NotificationService
from app.modules.settings.service import SettingsService
from testkit import UserFactory, auth


async def _notify(database: Database, user_id, **kwargs) -> None:  # type: ignore[no-untyped-def]
    async with database.session_factory() as s:
        await NotificationService(s).notify(user_id, kind="reminder", title="Your next step is ready", **kwargs)
        await s.commit()
        await dispatch_pending(s)


async def test_notify_delivers_on_chosen_channels_after_commit(
    database: Database, queue: InlineQueue, make_user: UserFactory, session: AsyncSession
) -> None:
    user = await make_user(reminder_channels={"in_app": True, "email": True, "whatsapp": False})
    await _notify(database, user.id)
    assert [j.name for j in queue.history] == ["notifications.deliver"]
    row = (await session.execute(Notification.__table__.select())).first()
    assert row is not None
    assert row.channel_status == {"in_app": "sent", "email": "simulated", "whatsapp": "skipped"}  # no email provider yet


async def test_rolled_back_work_never_reaches_the_queue(database: Database, queue: InlineQueue, make_user: UserFactory) -> None:
    user = await make_user()
    async with database.session_factory() as s:
        await NotificationService(s).notify(user.id, kind="system", title="x")
        await s.rollback()
        s.info.pop("pending_jobs", None)
    assert queue.history == []


async def test_stop_all_automatic_sends(database: Database, make_user: UserFactory, client: AsyncClient) -> None:
    user = await make_user()
    async with database.session_factory() as s:
        await SettingsService(s).set("workflows.automatic_sends_paused", True, None)
        await s.commit()
    await _notify(database, user.id, automatic=True)
    await _notify(database, user.id, automatic=False)  # people can still send by hand
    inbox = (await client.get("/me/notifications", headers=auth(user))).json()
    assert len(inbox["items"]) == 1 and inbox["unread"] == 1


async def test_inbox_read_flow(database: Database, make_user: UserFactory, client: AsyncClient) -> None:
    user = await make_user()
    other = await make_user()
    await _notify(database, user.id)
    await _notify(database, user.id)
    items = (await client.get("/me/notifications", headers=auth(user))).json()["items"]
    assert (await client.post(f"/me/notifications/{items[0]['id']}/read", headers=auth(other))).status_code == 404
    assert (await client.post(f"/me/notifications/{items[0]['id']}/read", headers=auth(user))).status_code == 204
    assert (await client.get("/me/notifications", headers=auth(user))).json()["unread"] == 1
    await client.post("/me/notifications/read-all", headers=auth(user))
    assert (await client.get("/me/notifications", headers=auth(user))).json()["unread"] == 0
