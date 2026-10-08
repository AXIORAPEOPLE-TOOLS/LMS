"""Graceful degradation helpers.

A `CircuitBreaker` stops calling a dependency that keeps failing (Redis, Groq,
email provider) for a cool-down period, so requests use the fallback path
immediately instead of waiting on timeouts. Breaker states feed /api/health,
which tells the frontend whether the product runs in full or limited mode.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any


class CircuitOpenError(Exception):
    """The dependency is temporarily switched off; use the fallback."""


@dataclass
class CircuitBreaker:
    name: str
    failure_threshold: int = 3
    reset_seconds: float = 30.0
    failures: int = 0
    opened_at: float | None = None
    last_error: str | None = field(default=None)

    @property
    def is_open(self) -> bool:
        if self.opened_at is None:
            return False
        # After the cool-down the breaker is half-open: one call may try again.
        return time.monotonic() - self.opened_at < self.reset_seconds

    @property
    def state(self) -> str:
        if self.opened_at is None:
            return "closed"
        return "open" if self.is_open else "half_open"

    def record_success(self) -> None:
        self.failures = 0
        self.opened_at = None
        self.last_error = None

    def record_failure(self, error: BaseException) -> None:
        self.failures += 1
        self.last_error = f"{type(error).__name__}: {error}"[:300]
        if self.failures >= self.failure_threshold:
            self.opened_at = time.monotonic()

    async def call[T](self, func: Callable[[], Awaitable[T]], *, timeout: float | None = None) -> T:
        if self.is_open:
            raise CircuitOpenError(self.name)
        try:
            result = await (asyncio.wait_for(func(), timeout) if timeout else func())
        except Exception as exc:
            self.record_failure(exc)
            raise
        self.record_success()
        return result


_breakers: dict[str, CircuitBreaker] = {}


def breaker(name: str, **kwargs: Any) -> CircuitBreaker:
    if name not in _breakers:
        _breakers[name] = CircuitBreaker(name, **kwargs)
    return _breakers[name]


def breaker_states() -> dict[str, str]:
    return {name: b.state for name, b in _breakers.items()}


def reset_breakers() -> None:
    _breakers.clear()
