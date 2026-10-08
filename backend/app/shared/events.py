"""Tiny in-process domain event bus.

Modules publish facts ("user.created", "assignment.completed") and other
modules subscribe, so features stay decoupled (e.g. the workflow engine
reacts to new people without the identity module knowing workflows exist).
"""

from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class DomainEvent:
    name: str
    payload: dict[str, Any] = field(default_factory=dict)


Handler = Callable[[AsyncSession, DomainEvent], Awaitable[None]]


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[str, list[Handler]] = defaultdict(list)

    def subscribe(self, event_name: str, handler: Handler) -> None:
        if handler not in self._handlers[event_name]:
            self._handlers[event_name].append(handler)

    async def publish(self, session: AsyncSession, event: DomainEvent) -> None:
        # Handlers run inside the caller's transaction: all-or-nothing.
        for handler in self._handlers.get(event.name, []):
            await handler(session, event)


event_bus = EventBus()
