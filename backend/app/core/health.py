"""Health, components and operating mode — for *every* external service.

Each dependency registers itself as a `Component` with a health check, whether
the product can run without it, and what the fallback is. /api/health walks the
registry, so adding a service (SMS, S3, SSO...) means one `register_component`.

/api/health/live  -> process is up (container liveness probe)
/api/health       -> every component + overall mode: "full", "limited" or "offline".
                     Always 200 so the frontend can read it and show a banner.
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter
from sqlalchemy import text

from app.core.config import get_settings
from app.core.database import get_database
from app.core.resilience import breaker, breaker_states

router = APIRouter(tags=["system"])

# Check result: "up" | "down" | "fallback" | informational ("inline", "basic", "log_only")
DEGRADED_STATES = {"down", "fallback"}


@dataclass(frozen=True)
class Component:
    name: str
    label: str  # plain words for the UI banner
    check: Callable[[], Awaitable[str]]
    critical: bool = False  # the product cannot work without it
    fallback: str = ""  # what happens while it is down


_components: dict[str, Component] = {}


def register_component(component: Component) -> None:
    _components[component.name] = component


async def _safe(check: Callable[[], Awaitable[str]]) -> str:
    try:
        return await asyncio.wait_for(check(), timeout=4)
    except Exception:
        return "down"


# ---- built-in components ----------------------------------------------------
async def _check_database() -> str:
    async with get_database().engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    breaker("database").record_success()
    return "up"


async def _check_queue() -> str:
    from app.core.queue import BullMQQueue, Queues, get_queue

    queue = get_queue()
    from app.core.sqs_queue import SQSQueue

    if isinstance(queue, SQSQueue):
        if breaker("sqs").is_open:
            return "fallback"
        try:
            await queue.url(Queues.NOTIFICATIONS)  # reachable and the queue exists
        except Exception:
            return "fallback"
        return "up"
    if not isinstance(queue, BullMQQueue):
        return "inline"
    if breaker("redis").is_open:
        return "fallback"
    import redis.asyncio as redis

    client = redis.from_url(queue.redis_url, socket_connect_timeout=3, socket_timeout=3)
    try:
        await client.ping()  # type: ignore[misc]  # redis stubs type ping() as bool | Awaitable
    except Exception:
        return "fallback"
    finally:
        await client.aclose()
    return "up"


async def _check_assistant() -> str:
    settings = get_settings()
    if settings.ai_provider != "groq" or not settings.groq_api_key:
        return "basic"
    return "fallback" if breaker("groq").is_open else "up"


def _channel_check(key: str) -> Callable[[], Awaitable[str]]:
    async def check() -> str:
        from app.modules.notifications.channels import CHANNELS

        channel = CHANNELS.get(key)
        if channel is None:
            return "down"
        if breaker(f"channel:{key}").is_open:
            return "fallback"
        return "log_only" if type(channel).__name__.startswith("Log") else "up"

    return check


async def _check_storage() -> str:
    from app.core.storage import get_storage

    return await get_storage().probe()


for _component in (
    Component(
        "database",
        "Database",
        _check_database,
        critical=True,
        fallback="The app shows the last loaded data and saving is paused.",
    ),
    Component(
        "queue", "Background jobs", _check_queue, fallback="Jobs run straight away inside the app instead of in the background."
    ),
    Component(
        "assistant", "Drafting and answers", _check_assistant, fallback="Drafts and answers use the built-in basic method."
    ),
    Component("email", "Email", _channel_check("email"), fallback="Messages still arrive in the app."),
    Component("whatsapp", "WhatsApp", _channel_check("whatsapp"), fallback="Messages still arrive in the app."),
    Component("storage", "File storage", _check_storage, fallback="File uploads are paused."),
):
    register_component(_component)


async def health_report() -> dict[str, Any]:
    names = list(_components)
    results = await asyncio.gather(*(_safe(_components[n].check) for n in names))
    states = dict(zip(names, results, strict=True))
    degraded = [n for n in names if states[n] in DEGRADED_STATES]
    if any(_components[n].critical for n in degraded):
        mode = "offline"
    elif degraded:
        mode = "limited"
    else:
        mode = "full"
    return {
        "status": "degraded" if mode == "offline" else "ok",
        "mode": mode,
        "components": states,
        "degraded": [{"name": n, "label": _components[n].label, "fallback": _components[n].fallback} for n in degraded],
        "breakers": breaker_states(),
    }


@router.get("/health/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health")
async def health() -> dict[str, Any]:
    return await health_report()
