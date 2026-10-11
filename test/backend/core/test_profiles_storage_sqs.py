"""Deploy profiles (development / single / scalable), file storage, and the SQS queue + consumer."""

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from app.core.config import Settings
from app.core.queue import Job, Queues
from app.core.sqs_queue import MAX_DELAY_SECONDS, SQSConsumer, SQSQueue
from app.core.storage import LocalStorage


# ---- profiles -------------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """The test run pins some LMS_ variables; profiles must be tested without them."""
    for name in ("LMS_DEPLOY_PROFILE", "LMS_QUEUE_BACKEND", "LMS_STORAGE_BACKEND", "LMS_REDIS_URL", "LMS_S3_BUCKET"):
        monkeypatch.delenv(name, raising=False)


def test_each_profile_picks_its_queue_and_storage() -> None:
    dev = Settings(_env_file=None)
    single = Settings(_env_file=None, deploy_profile="single", redis_url="redis://localhost:6379")
    scalable = Settings(_env_file=None, deploy_profile="scalable", s3_bucket="lms-files")
    assert (dev.queue_backend, dev.storage_backend) == ("inline", "local")
    assert (single.queue_backend, single.storage_backend) == ("bullmq", "local")
    assert (scalable.queue_backend, scalable.storage_backend) == ("sqs", "s3")


def test_empty_values_follow_the_profile() -> None:
    settings = Settings(_env_file=None, deploy_profile="single", redis_url="redis://x", queue_backend="", storage_backend=" ")
    assert (settings.queue_backend, settings.storage_backend) == ("bullmq", "local")


def test_a_part_can_be_overridden() -> None:
    settings = Settings(_env_file=None, queue_backend="sqs", sqs_endpoint_url="http://localhost:9324")
    assert settings.queue_backend == "sqs" and settings.storage_backend == "local"  # try ElasticMQ in development


@pytest.mark.parametrize(
    ("fields", "missing"),
    [
        ({"deploy_profile": "single"}, "LMS_REDIS_URL"),
        ({"deploy_profile": "scalable"}, "LMS_S3_BUCKET"),
        ({"deploy_profile": "scalable", "s3_bucket": "b", "storage_backend": "local"}, "LMS_STORAGE_BACKEND=s3"),
    ],
)
def test_a_profile_missing_something_fails_at_start(fields: dict[str, Any], missing: str) -> None:
    with pytest.raises(ValueError, match=missing):
        Settings(_env_file=None, **fields)


# ---- local storage --------------------------------------------------------------------------
async def test_local_storage_saves_reads_and_deletes_by_key(tmp_path: Path) -> None:
    store = LocalStorage(str(tmp_path))
    key = await store.save("knowledge/abc-sop.pdf", b"hello")
    assert key == "knowledge/abc-sop.pdf" and (tmp_path / key).read_bytes() == b"hello"
    assert await store.read(key) == b"hello"
    await store.delete(key)
    assert not (tmp_path / key).exists()
    assert await store.probe() == "up"


async def test_local_storage_reads_old_full_paths_and_blocks_escapes(tmp_path: Path) -> None:
    store = LocalStorage(str(tmp_path / "uploads"))
    old = tmp_path / "uploads" / "knowledge" / "old.pdf"
    old.parent.mkdir(parents=True)
    old.write_bytes(b"from before keys")
    assert await store.read(str(old)) == b"from before keys"
    from app.core.errors import NotFoundError

    with pytest.raises(NotFoundError):
        await store.read("../../etc/passwd")


# ---- SQS ------------------------------------------------------------------------------------
class FakeSQS:
    """Just enough of the SQS client for the queue and the consumer."""

    class exceptions:  # noqa: N801  (mirrors botocore's attribute)
        class QueueDoesNotExist(Exception):
            pass

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.deleted: list[str] = []
        self.visibility: list[int] = []
        self.inbox: list[dict[str, Any]] = []

    async def get_queue_url(self, QueueName: str) -> dict[str, str]:  # noqa: N803
        return {"QueueUrl": f"https://sqs/{QueueName}"}

    async def send_message_batch(self, QueueUrl: str, Entries: list[dict[str, Any]]) -> dict[str, Any]:  # noqa: N803
        self.sent.append({"url": QueueUrl, "entries": Entries})
        return {"Successful": Entries}

    async def send_message(self, **kwargs: Any) -> None:
        self.sent.append({"url": kwargs["QueueUrl"], "entries": [kwargs]})

    async def receive_message(self, **_: Any) -> dict[str, Any]:
        messages, self.inbox = self.inbox, []
        if not messages:
            await asyncio.sleep(0.01)
        return {"Messages": messages}

    async def delete_message(self, QueueUrl: str, ReceiptHandle: str) -> None:  # noqa: N803
        self.deleted.append(ReceiptHandle)

    async def change_message_visibility(self, QueueUrl: str, ReceiptHandle: str, VisibilityTimeout: int) -> None:  # noqa: N803
        self.visibility.append(VisibilityTimeout)


def _queue(fake: FakeSQS) -> SQSQueue:
    queue = SQSQueue()
    queue._client = fake
    return queue


async def test_jobs_are_sent_ten_per_call_to_the_right_queue() -> None:
    fake = FakeSQS()
    jobs = [Job(Queues.NOTIFICATIONS, "notifications.deliver", {"id": str(i)}) for i in range(23)]
    await _queue(fake).enqueue_many([*jobs, Job(Queues.AUTHORING, "agents.run", {"id": "x"})])
    sizes = [(call["url"].rsplit("/", 1)[-1], len(call["entries"])) for call in fake.sent]
    assert sizes == [("lms-notifications", 10), ("lms-notifications", 10), ("lms-notifications", 3), ("lms-authoring", 1)]
    assert json.loads(fake.sent[0]["entries"][0]["MessageBody"])["name"] == "notifications.deliver"


def test_delays_over_fifteen_minutes_carry_a_due_time() -> None:
    body, delay = SQSQueue.body("notifications.deliver", {"id": "a"}, delay_ms=3 * 60 * 60 * 1000)
    assert delay == MAX_DELAY_SECONDS and "not_before" in json.loads(body)
    body, delay = SQSQueue.body("notifications.deliver", {"id": "a"}, delay_ms=60_000)
    assert delay == 60 and "not_before" not in json.loads(body)


async def _consume(fake: FakeSQS, run: Any, messages: list[dict[str, Any]]) -> None:
    stop = asyncio.Event()
    fake.inbox = messages
    consumer = SQSConsumer(_queue(fake), (Queues.NOTIFICATIONS,), run, stop)
    task = asyncio.create_task(consumer.serve())
    await asyncio.sleep(0.1)
    stop.set()
    await asyncio.wait_for(task, 2)


def _message(receipt: str, receives: int, **body: Any) -> dict[str, Any]:
    payload = {"name": "notifications.deliver", "data": {"id": "n1"}, **body}
    return {"ReceiptHandle": receipt, "MessageId": receipt, "Body": json.dumps(payload), "Attributes": {"ApproximateReceiveCount": str(receives)}}


async def test_done_jobs_are_deleted_and_failed_ones_come_back_later() -> None:
    fake = FakeSQS()
    seen: list[tuple[str, int]] = []

    async def run(name: str, data: dict[str, Any], job_id: str, attempt: int) -> None:
        seen.append((job_id, attempt))
        if job_id != "ok":
            raise RuntimeError("provider down")

    await _consume(fake, run, [_message("ok", 1), _message("retry", 2), _message("last", 5)])
    assert ("ok", 1) in seen and ("retry", 2) in seen
    assert fake.deleted == ["ok"]  # failures are not deleted: SQS shows them again
    assert sorted(fake.visibility) == [0, 10]  # attempt 2 waits 10 s; the last attempt goes to the dead-letter queue now


async def test_a_message_not_due_yet_is_sent_on_instead_of_run() -> None:
    import time

    fake = FakeSQS()
    ran: list[str] = []

    async def run(name: str, data: dict[str, Any], job_id: str, attempt: int) -> None:
        ran.append(job_id)

    await _consume(fake, run, [_message("later", 1, not_before=time.time() + 3600)])
    assert ran == [] and fake.deleted == ["later"]
    hop = fake.sent[-1]["entries"][0]
    assert hop["DelaySeconds"] == MAX_DELAY_SECONDS and "not_before" in json.loads(hop["MessageBody"])
