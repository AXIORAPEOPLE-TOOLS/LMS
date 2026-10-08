"""Admin monitoring snapshot: server, API load, database, Redis/BullMQ, scheduler, workflows, breakers."""

import asyncio
import os
import platform
import sys
import time
from typing import Any

import psutil
from sqlalchemy import func, select, text

from app.core.config import get_settings
from app.core.database import get_database
from app.core.health import health_report
from app.core.queue import BullMQQueue, Queues, get_queue
from app.core.resilience import _breakers, breaker
from app.modules.monitoring.collector import metrics

_process = psutil.Process(os.getpid())
_process.cpu_percent(None)  # prime the counter


def server_stats() -> dict[str, Any]:
    memory = psutil.virtual_memory()
    try:
        disk = psutil.disk_usage(os.path.abspath(get_settings().upload_dir if os.path.exists(get_settings().upload_dir) else "."))
        disk_pct = disk.percent
        disk_free_gb = round(disk.free / 1e9, 1)
    except Exception:
        disk_pct, disk_free_gb = 0.0, 0.0
    load = None
    if hasattr(os, "getloadavg"):
        load = [round(v, 2) for v in os.getloadavg()]
    return {
        "cpu_pct": psutil.cpu_percent(interval=None),
        "cpu_count": psutil.cpu_count(),
        "process_cpu_pct": round(_process.cpu_percent(None), 1),
        "memory_pct": memory.percent,
        "memory_used_gb": round(memory.used / 1e9, 2),
        "memory_total_gb": round(memory.total / 1e9, 2),
        "process_memory_mb": round(_process.memory_info().rss / 1e6, 1),
        "threads": _process.num_threads(),
        "disk_pct": disk_pct,
        "disk_free_gb": disk_free_gb,
        "load_avg": load,
        "python": sys.version.split()[0],
        "platform": f"{platform.system()} {platform.release()}",
        "pid": os.getpid(),
        "environment": get_settings().environment,
    }


async def database_stats() -> dict[str, Any]:
    db = get_database()
    pool = db.engine.pool
    started = time.perf_counter()
    stats: dict[str, Any] = {"dialect": db.engine.dialect.name}
    try:
        async with db.engine.connect() as conn:
            await asyncio.wait_for(conn.execute(text("SELECT 1")), timeout=4)
            stats["latency_ms"] = round((time.perf_counter() - started) * 1000, 1)
            if db.engine.dialect.name == "postgresql":
                size = await conn.scalar(text("SELECT pg_database_size(current_database())"))
                connections = await conn.scalar(text("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()"))
                stats["size_mb"] = round((size or 0) / 1e6, 1)
                stats["server_connections"] = connections
        stats["status"] = "up"
    except Exception as exc:
        stats["status"] = "down"
        stats["error"] = type(exc).__name__
    for attr in ("size", "checkedout", "overflow"):
        method = getattr(pool, attr, None)
        if callable(method):
            stats[f"pool_{attr}"] = method()
    return stats


async def table_counts() -> dict[str, int]:
    from app.modules.identity.models import User
    from app.modules.knowledge.models import KnowledgeItem
    from app.modules.learning.models import Assignment, Course
    from app.modules.notifications.models import Notification

    out: dict[str, int] = {}
    try:
        async with get_database().session_factory() as session:
            for label, model in (
                ("people", User),
                ("courses", Course),
                ("assignments", Assignment),
                ("knowledge_items", KnowledgeItem),
                ("messages", Notification),
            ):
                out[label] = int(await session.scalar(select(func.count()).select_from(model)) or 0)
    except Exception:
        pass
    return out


async def redis_stats() -> dict[str, Any]:
    settings = get_settings()
    queue = get_queue()
    if not isinstance(queue, BullMQQueue) or not settings.redis_url:
        return {
            "status": "inline",
            "queues": [{"name": n, "waiting": 0, "active": 0, "delayed": 0, "failed": 0, "completed": 0} for n in Queues.ALL],
        }
    if breaker("redis").is_open:
        return {"status": "fallback", "queues": []}
    import redis.asyncio as redis

    client = redis.from_url(settings.redis_url, socket_connect_timeout=3, socket_timeout=3)
    out: dict[str, Any] = {"status": "up", "queues": []}
    try:
        started = time.perf_counter()
        await client.ping()  # type: ignore[misc]
        out["latency_ms"] = round((time.perf_counter() - started) * 1000, 1)
        info = await client.info()
        out["version"] = info.get("redis_version")
        out["used_memory_mb"] = round(int(info.get("used_memory", 0)) / 1e6, 2)
        out["clients"] = info.get("connected_clients")
        out["ops_per_sec"] = info.get("instantaneous_ops_per_sec")
        for name in Queues.ALL:
            prefix = f"bull:{name}"
            pipe = client.pipeline()
            pipe.llen(f"{prefix}:wait")
            pipe.llen(f"{prefix}:active")
            pipe.zcard(f"{prefix}:delayed")
            pipe.zcard(f"{prefix}:failed")
            pipe.zcard(f"{prefix}:completed")
            pipe.zcard(f"{prefix}:prioritized")
            waiting, active, delayed, failed, completed, prioritized = await pipe.execute()
            out["queues"].append(
                {
                    "name": name,
                    "waiting": waiting + prioritized,
                    "active": active,
                    "delayed": delayed,
                    "failed": failed,
                    "completed": completed,
                }
            )
    except Exception as exc:
        out["status"] = "down"
        out["error"] = type(exc).__name__
    finally:
        await client.aclose()
    return out


async def scheduler_and_workflows() -> dict[str, Any]:
    from app.modules.scheduler.models import TaskRun
    from app.modules.scheduler.registry import tasks
    from app.modules.workflows.models import Workflow, WorkflowRun

    try:
        async with get_database().session_factory() as session:
            runs = {r.name: r for r in (await session.scalars(select(TaskRun))).all()}
            pending = int(await session.scalar(select(func.count()).where(WorkflowRun.status == "pending_approval")) or 0)
            failed = int(await session.scalar(select(func.count()).where(WorkflowRun.status == "failed")) or 0)
            recent = (
                await session.execute(
                    select(WorkflowRun, Workflow.name)
                    .join(Workflow, Workflow.id == WorkflowRun.workflow_id)
                    .order_by(WorkflowRun.created_at.desc())
                    .limit(6)
                )
            ).all()
    except Exception:
        return {"tasks": [], "workflows": {"pending": 0, "failed": 0, "recent": []}}
    return {
        "tasks": [
            {
                "name": t.name,
                "every": t.every,
                "last_run_at": runs[t.name].last_run_at.isoformat() if t.name in runs else None,
                "last_result": runs[t.name].last_result if t.name in runs else None,
            }
            for t in tasks()
        ],
        "workflows": {
            "pending": pending,
            "failed": failed,
            "recent": [
                {"name": name, "status": r.status, "triggered_by": r.triggered_by, "at": r.created_at.isoformat()}
                for r, name in recent
            ],
        },
    }


def breakers() -> list[dict[str, Any]]:
    return [
        {"name": name, "state": b.state, "failures": b.failures, "last_error": b.last_error}
        for name, b in sorted(_breakers.items())
    ]


async def snapshot() -> dict[str, Any]:
    health, database, redis_info, ops, counts = await asyncio.gather(
        health_report(), database_stats(), redis_stats(), scheduler_and_workflows(), table_counts()
    )
    return {
        "generated_at": time.time(),
        "mode": health["mode"],
        "components": health["components"],
        "server": server_stats(),
        "api": {**metrics.summary(), "timeline": metrics.timeline(), "routes": metrics.routes(), "errors": metrics.errors()},
        "database": {**database, "counts": counts},
        "redis": redis_info,
        "scheduler": ops["tasks"],
        "workflows": ops["workflows"],
        "breakers": breakers(),
    }
