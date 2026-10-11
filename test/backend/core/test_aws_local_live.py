"""The real SQS and S3 clients against local stand-ins (ElasticMQ + S3Mock). Skipped unless they are running:

    docker compose -f deploy/compose.aws-local.yml up -d
    LMS_LIVE_AWS_LOCAL=1 uv run --project backend pytest test/backend/core/test_aws_local_live.py
"""

import asyncio
import os
import uuid
from typing import Any

import pytest

from app.core import config
from app.core.queue import Job, Queues
from app.core.sqs_queue import SQSConsumer, SQSQueue
from app.core.storage import S3Storage

pytestmark = pytest.mark.skipif(os.environ.get("LMS_LIVE_AWS_LOCAL") != "1", reason="needs deploy/compose.aws-local.yml")

SQS_URL = os.environ.get("LMS_LIVE_SQS_URL", "http://localhost:9324")
S3_URL = os.environ.get("LMS_LIVE_S3_URL", "http://localhost:9000")


@pytest.fixture(autouse=True)
def _local_aws(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in {"AWS_ACCESS_KEY_ID": "local", "AWS_SECRET_ACCESS_KEY": "localsecret", "AWS_REGION": "ap-southeast-1"}.items():
        monkeypatch.setenv(name, value)
    settings = config.get_settings()
    # Fresh queue names per run, quick retries so the test is fast.
    for key, value in {
        "sqs_endpoint_url": SQS_URL,
        "sqs_queue_prefix": f"t{uuid.uuid4().hex[:8]}-",
        "sqs_create_queues": True,
        "sqs_wait_seconds": 1,
        "sqs_visibility_seconds": 5,
        "job_backoff_ms": 1000,
        "job_attempts": 2,
        "worker_concurrency": 4,
    }.items():
        monkeypatch.setattr(settings, key, value)


async def test_s3_storage_round_trip() -> None:
    store = S3Storage("lms-files", "test", "ap-southeast-1", S3_URL)
    assert await store.probe() == "up"
    key = f"knowledge/{uuid.uuid4().hex}-sop.pdf"
    await store.save(key, b"%PDF real bytes", "application/pdf")
    assert await store.read(key) == b"%PDF real bytes"
    await store.delete(key)
    from app.core.errors import NotFoundError

    with pytest.raises(NotFoundError):
        await store.read(key)


async def _wait(check: Any, seconds: float = 20) -> None:
    for _ in range(int(seconds * 10)):
        if await check():
            return
        await asyncio.sleep(0.1)
    raise AssertionError("timed out")


async def test_jobs_run_retry_and_end_in_the_dead_letter_queue() -> None:
    queue = SQSQueue()
    stop = asyncio.Event()
    attempts: dict[str, int] = {}

    async def run(name: str, data: dict[str, Any], job_id: str, attempt: int) -> None:
        key = data["key"]
        attempts[key] = attempts.get(key, 0) + 1
        if key == "flaky" and attempt == 1:
            raise RuntimeError("provider blinked")  # works on the retry
        if key == "broken":
            raise RuntimeError("always fails")  # ends in the dead-letter queue

    jobs = [Job(Queues.NOTIFICATIONS, "notifications.deliver", {"key": f"ok{i}"}) for i in range(23)]
    jobs += [Job(Queues.NOTIFICATIONS, "notifications.deliver", {"key": k}) for k in ("flaky", "broken")]
    try:
        await queue.enqueue_many(jobs)  # 25 jobs = 3 batch calls
        consumer = asyncio.create_task(SQSConsumer(queue, (Queues.NOTIFICATIONS,), run, stop).serve())

        async def all_done() -> bool:
            ok = all(attempts.get(f"ok{i}") for i in range(23))
            return ok and attempts.get("flaky", 0) >= 2 and attempts.get("broken", 0) >= 2

        await _wait(all_done)

        async def dead_lettered() -> bool:
            return (await queue.depth(Queues.NOTIFICATIONS)).get("dlq_waiting", 0) >= 1

        await _wait(dead_lettered)  # moved there on the receive after the last attempt
        assert all(attempts[f"ok{i}"] == 1 for i in range(23))  # each done once, deleted
        assert attempts["flaky"] == 2
    finally:
        stop.set()
        await asyncio.wait_for(consumer, 15)
        await queue.close()


async def test_a_long_delay_hops_until_due() -> None:
    queue = SQSQueue()
    body, delay = queue.body("notifications.deliver", {"key": "later"}, delay_ms=2 * 60 * 60 * 1000)
    assert delay == 900 and "not_before" in body
    try:
        sqs = await queue.client()
        url = await queue.url(Queues.REPORTS)
        await sqs.send_message(QueueUrl=url, MessageBody=body)  # due in 2 h, sent without delay to test the hop
        stop = asyncio.Event()
        ran: list[str] = []

        async def run(name: str, data: dict[str, Any], job_id: str, attempt: int) -> None:
            ran.append(data["key"])

        consumer = asyncio.create_task(SQSConsumer(queue, (Queues.REPORTS,), run, stop).serve())

        async def hopped() -> bool:
            return (await queue.depth(Queues.REPORTS)).get("delayed", 0) >= 1

        await _wait(hopped)
        stop.set()
        await asyncio.wait_for(consumer, 15)
        assert ran == []  # not run early; waiting in the queue again with a 15-minute delay
    finally:
        await queue.close()
