"""In-process request metrics: per-minute buckets, per-route latency, recent errors.

Cheap enough to run on every request (O(1) per request, bounded memory). Each API
process keeps its own numbers; the monitoring page shows the process it talks to.
"""

import time
from collections import deque
from dataclasses import dataclass, field
from threading import Lock

WINDOW_MINUTES = 60
MAX_SAMPLES_PER_ROUTE = 500
MAX_ERRORS = 50


@dataclass
class MinuteBucket:
    minute: int
    requests: int = 0
    errors: int = 0  # 5xx
    client_errors: int = 0  # 4xx
    total_ms: float = 0.0


@dataclass
class RouteStats:
    count: int = 0
    errors: int = 0
    samples: deque[float] = field(default_factory=lambda: deque(maxlen=MAX_SAMPLES_PER_ROUTE))


class MetricsCollector:
    def __init__(self) -> None:
        self.started_at = time.time()
        self._lock = Lock()
        self._minutes: deque[MinuteBucket] = deque(maxlen=WINDOW_MINUTES)
        self._routes: dict[str, RouteStats] = {}
        self._errors: deque[dict[str, object]] = deque(maxlen=MAX_ERRORS)
        self.in_flight = 0
        self.total_requests = 0

    def _bucket(self, now: float) -> MinuteBucket:
        minute = int(now // 60)
        if not self._minutes or self._minutes[-1].minute != minute:
            self._minutes.append(MinuteBucket(minute))
        return self._minutes[-1]

    def record(self, method: str, route: str, status: int, duration_ms: float) -> None:
        with self._lock:
            bucket = self._bucket(time.time())
            bucket.requests += 1
            bucket.total_ms += duration_ms
            if status >= 500:
                bucket.errors += 1
            elif status >= 400:
                bucket.client_errors += 1
            stats = self._routes.setdefault(f"{method} {route}", RouteStats())
            stats.count += 1
            stats.samples.append(duration_ms)
            if status >= 500:
                stats.errors += 1
            self.total_requests += 1

    def record_error(self, path: str, code: str, message: str, request_id: str | None) -> None:
        with self._lock:
            self._errors.appendleft(
                {"at": time.time(), "path": path, "code": code, "message": message[:200], "request_id": request_id}
            )

    def timeline(self) -> list[dict[str, float]]:
        """Last 30 minutes, one point per minute (missing minutes are zeros)."""
        now_minute = int(time.time() // 60)
        with self._lock:
            by_minute = {b.minute: b for b in self._minutes}
        points = []
        for minute in range(now_minute - 29, now_minute + 1):
            b = by_minute.get(minute)
            points.append(
                {
                    "t": minute * 60,
                    "requests": b.requests if b else 0,
                    "errors": b.errors if b else 0,
                    "avg_ms": round(b.total_ms / b.requests, 1) if b and b.requests else 0,
                }
            )
        return points

    def routes(self, limit: int = 8) -> list[dict[str, object]]:
        with self._lock:
            items = [(name, stats.count, stats.errors, sorted(stats.samples)) for name, stats in self._routes.items()]
        out = []
        for name, count, errors, samples in sorted(items, key=lambda r: -r[1])[:limit]:
            out.append(
                {
                    "route": name,
                    "count": count,
                    "errors": errors,
                    "p50_ms": round(_percentile(samples, 50), 1),
                    "p95_ms": round(_percentile(samples, 95), 1),
                }
            )
        return out

    def summary(self) -> dict[str, float]:
        recent = self.timeline()[-5:]
        requests = sum(p["requests"] for p in recent)
        errors = sum(p["errors"] for p in recent)
        with self._lock:
            all_samples = sorted(s for stats in self._routes.values() for s in stats.samples)
        return {
            "requests_per_minute": round(requests / 5, 1),
            "error_rate_pct": round(errors / requests * 100, 2) if requests else 0.0,
            "p50_ms": round(_percentile(all_samples, 50), 1),
            "p95_ms": round(_percentile(all_samples, 95), 1),
            "in_flight": self.in_flight,
            "total_requests": self.total_requests,
            "uptime_seconds": round(time.time() - self.started_at),
        }

    def errors(self) -> list[dict[str, object]]:
        with self._lock:
            return list(self._errors)


def _percentile(sorted_values: list[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    index = min(len(sorted_values) - 1, max(0, round(pct / 100 * (len(sorted_values) - 1))))
    return sorted_values[index]


metrics = MetricsCollector()
