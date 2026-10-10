"""Amazon SQS backend for the job queue (scalable profile), and the worker loop that consumes it.

Same contract as BullMQ: the API sends jobs after its transaction commits, the worker runs them.

- One SQS queue per logical queue ("lms-notifications", ...) plus a dead-letter queue ("lms-notifications-dlq").
- Sending: SendMessageBatch, 10 per call (the SQS limit).
- Delays: SQS can delay at most 15 minutes. Longer delays carry a "not_before" time; the worker
  puts such a message back with the remaining delay (max 15 minutes each hop) until it is due.
- Retries: a failed job is not deleted; it becomes visible again after a growing delay
  (job_backoff_ms * 2^(attempt-1)). After job_attempts receives SQS moves it to the dead-letter queue.
- Long jobs: while a job runs its visibility is extended, so another worker never picks it up twice.
- SQS delivers at least once; job handlers are idempotent (deliveries lock their row, helper runs check status).
- Local development: point LMS_SQS_ENDPOINT_URL at ElasticMQ (docker compose -f deploy/docker-compose.dev.yml).
"""

import asyncio
import contextlib
import json
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from app.core.config import get_settings
from app.core.resilience import breaker

logger = logging.getLogger("queue.sqs")

MAX_DELAY_SECONDS = 900  # SQS limit
MAX_VISIBILITY_SECONDS = 43_200  # SQS limit (12 h)


class SQSQueue:
    def __init__(self) -> None:
        import aioboto3

        settings = get_settings()
        self.prefix = settings.sqs_queue_prefix
        self.session = aioboto3.Session()
        self.client_args: dict[str, Any] = {"region_name": settings.aws_region, "endpoint_url": settings.sqs_endpoint_url}
        self._client: Any = None
        self._stack: contextlib.AsyncExitStack | None = None
        self._urls: dict[str, str] = {}
        self._lock = asyncio.Lock()

    async def client(self) -> Any:
        async with self._lock:
            if self._client is None:
                self._stack = contextlib.AsyncExitStack()
                self._client = await self._stack.enter_async_context(self.session.client("sqs", **self.client_args))
        return self._client

    async def url(self, name: str) -> str:
        """Queue URL for a logical queue name; creates the queue and its dead-letter queue when allowed."""
        if name in self._urls:
            return self._urls[name]
        sqs = await self.client()
        full = f"{self.prefix}{name}"
        try:
            url = (await sqs.get_queue_url(QueueName=full))["QueueUrl"]
        except sqs.exceptions.QueueDoesNotExist:
            if not get_settings().sqs_create_queues:
                raise
            url = await self._create(sqs, full)
        self._urls[name] = url
        return url

    @staticmethod
    async def _create(sqs: Any, full: str) -> str:
        settings = get_settings()
        dlq_url = (await sqs.create_queue(QueueName=f"{full}-dlq", Attributes={"MessageRetentionPeriod": "1209600"}))["QueueUrl"]
        dlq_arn = (await sqs.get_queue_attributes(QueueUrl=dlq_url, AttributeNames=["QueueArn"]))["Attributes"]["QueueArn"]
        redrive = json.dumps({"deadLetterTargetArn": dlq_arn, "maxReceiveCount": str(settings.job_attempts)})
        attributes = {
            "VisibilityTimeout": str(settings.sqs_visibility_seconds),
            "ReceiveMessageWaitTimeSeconds": str(settings.sqs_wait_seconds),
            "RedrivePolicy": redrive,
        }
        logger.info("Created SQS queue %s with dead-letter queue %s-dlq", full, full)
        return (await sqs.create_queue(QueueName=full, Attributes=attributes))["QueueUrl"]

    @staticmethod
    def body(name: str, data: dict[str, Any], delay_ms: int) -> tuple[str, int]:
        """Message body and the SQS delay (seconds, max 15 minutes)."""
        payload: dict[str, Any] = {"name": name, "data": data}
        delay = max(0, delay_ms // 1000)
        if delay > MAX_DELAY_SECONDS:
            payload["not_before"] = time.time() + delay
            delay = MAX_DELAY_SECONDS
        return json.dumps(payload), delay

    async def enqueue(self, job: Any) -> None:
        await self.enqueue_many([job])

    async def enqueue_many(self, jobs: list[Any]) -> None:
        by_queue: dict[str, list[Any]] = {}
        for job in jobs:
            by_queue.setdefault(job.queue, []).append(job)
        for name, items in by_queue.items():
            for start in range(0, len(items), 10):
                entries = []
                for i, job in enumerate(items[start : start + 10]):
                    body, delay = self.body(job.name, job.data, job.delay_ms)
                    entries.append({"Id": str(i), "MessageBody": body, "DelaySeconds": delay})
                await breaker("sqs", failure_threshold=2).call(lambda n=name, e=entries: self._send(n, e), timeout=10)

    async def _send(self, name: str, entries: list[dict[str, Any]]) -> None:
        sqs = await self.client()
        url = await self.url(name)
        result = await sqs.send_message_batch(QueueUrl=url, Entries=entries)
        failed = result.get("Failed") or []
        if failed:  # retry just the failed entries once; handlers are idempotent if one went through
            again = [e for e in entries if e["Id"] in {f["Id"] for f in failed}]
            result = await sqs.send_message_batch(QueueUrl=url, Entries=again)
            if result.get("Failed"):
                raise RuntimeError(f"SQS refused {len(result['Failed'])} messages on {name}")

    async def depth(self, name: str) -> dict[str, int]:
        """Backlog for the heartbeat and monitoring."""
        sqs = await self.client()
        out: dict[str, int] = {}
        for label, queue in (("", name), ("dlq_", f"{name}-dlq")):
            try:
                url = await self.url(queue)
                attrs = (
                    await sqs.get_queue_attributes(
                        QueueUrl=url,
                        AttributeNames=[
                            "ApproximateNumberOfMessages",
                            "ApproximateNumberOfMessagesNotVisible",
                            "ApproximateNumberOfMessagesDelayed",
                        ],
                    )
                )["Attributes"]
            except Exception:
                continue
            out[f"{label}waiting"] = int(attrs.get("ApproximateNumberOfMessages", 0))
            out[f"{label}active"] = int(attrs.get("ApproximateNumberOfMessagesNotVisible", 0))
            out[f"{label}delayed"] = int(attrs.get("ApproximateNumberOfMessagesDelayed", 0))
        return out

    async def close(self) -> None:
        if self._stack:
            await self._stack.aclose()
        self._client, self._stack = None, None


Runner = Callable[[str, dict[str, Any], str, int], Awaitable[Any]]


class SQSConsumer:
    """Worker side: long-polls each queue and runs up to `concurrency` jobs at a time per queue."""

    def __init__(self, queue: SQSQueue, names: tuple[str, ...], run: Runner, stop: asyncio.Event) -> None:
        settings = get_settings()
        self.queue = queue
        self.names = names
        self.run = run
        self.stop = stop
        self.concurrency = settings.worker_concurrency
        self.visibility = settings.sqs_visibility_seconds
        self.wait = settings.sqs_wait_seconds
        self.attempts = settings.job_attempts
        self.backoff_ms = settings.job_backoff_ms

    async def serve(self) -> None:
        await asyncio.gather(*(self._poll(name) for name in self.names))

    async def _poll(self, name: str) -> None:
        sqs = await self.queue.client()
        url = await self.queue.url(name)
        slots = asyncio.Semaphore(self.concurrency)
        running: set[asyncio.Task[None]] = set()
        while not self.stop.is_set():
            free = max(1, min(10, self.concurrency - len(running)))
            try:
                response = await sqs.receive_message(
                    QueueUrl=url,
                    MaxNumberOfMessages=free,
                    WaitTimeSeconds=self.wait,
                    AttributeNames=["ApproximateReceiveCount"],
                )
            except Exception:
                logger.exception("Could not read from %s; trying again in 5 s", name)
                await asyncio.sleep(5)
                continue
            for message in response.get("Messages", []):
                await slots.acquire()
                task = asyncio.create_task(self._handle(sqs, url, name, message, slots))
                running.add(task)
                task.add_done_callback(running.discard)
        # Shutting down (deploy or Spot interruption): finish what is running; the rest stays in the queue.
        if running:
            logger.info("Stopping %s: finishing %s running job(s)", name, len(running))
            await asyncio.gather(*running, return_exceptions=True)

    async def _handle(self, sqs: Any, url: str, name: str, message: dict[str, Any], slots: asyncio.Semaphore) -> None:
        receipt = message["ReceiptHandle"]
        try:
            payload = json.loads(message["Body"])
            not_before = payload.get("not_before")
            if not_before and not_before > time.time() + 1:
                # Not due yet (delays over 15 minutes): send it on with the remaining delay.
                remaining = int(not_before - time.time())
                body = dict(payload)
                if remaining <= MAX_DELAY_SECONDS:
                    body.pop("not_before")
                await sqs.send_message(QueueUrl=url, MessageBody=json.dumps(body), DelaySeconds=min(remaining, MAX_DELAY_SECONDS))
                await sqs.delete_message(QueueUrl=url, ReceiptHandle=receipt)
                return
            attempt = int(message.get("Attributes", {}).get("ApproximateReceiveCount", "1"))
            keeper = asyncio.create_task(self._keep_hidden(sqs, url, receipt))
            try:
                await self.run(payload["name"], payload.get("data") or {}, message["MessageId"], attempt)
            except Exception:
                # Show it again after a growing delay (5 s, 10 s, 20 s, ...). After the last attempt it is shown
                # at once, and on that receive SQS moves it to the dead-letter queue.
                delay = 0
                if attempt < self.attempts:
                    delay = min(MAX_VISIBILITY_SECONDS, self.backoff_ms * 2 ** (attempt - 1) // 1000)
                with contextlib.suppress(Exception):
                    await sqs.change_message_visibility(QueueUrl=url, ReceiptHandle=receipt, VisibilityTimeout=delay)
                return
            finally:
                keeper.cancel()
            await sqs.delete_message(QueueUrl=url, ReceiptHandle=receipt)
        except Exception:
            logger.exception("Could not handle a message from %s", name)
        finally:
            slots.release()

    async def _keep_hidden(self, sqs: Any, url: str, receipt: str) -> None:
        """Long jobs (course drafting) extend their visibility so no other worker starts them."""
        with contextlib.suppress(asyncio.CancelledError):
            while True:
                await asyncio.sleep(max(10, self.visibility // 2))
                with contextlib.suppress(Exception):
                    await sqs.change_message_visibility(QueueUrl=url, ReceiptHandle=receipt, VisibilityTimeout=self.visibility)
