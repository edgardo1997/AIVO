"""Async EventBus — pub/sub foundation for Sentinel's Live Activity system."""

import asyncio
import logging
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set

from sentinel.core.events import SentinelEvent
from sentinel.core.event_registry import EventRegistry

logger = logging.getLogger(__name__)

EventHandler = Callable[[SentinelEvent], Coroutine[Any, Any, None]]


class EventBus:
    def __init__(self, registry: Optional[EventRegistry] = None):
        self._registry = registry or EventRegistry()
        self._subscribers: Dict[str, List[EventHandler]] = {}
        self._wildcard_subscribers: List[EventHandler] = []

    @property
    def registry(self) -> EventRegistry:
        return self._registry

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        if event_type == "*":
            self._wildcard_subscribers.append(handler)
        else:
            self._registry.validate(event_type)
            self._subscribers.setdefault(event_type, []).append(handler)

    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        if event_type == "*":
            self._wildcard_subscribers.remove(handler)
        else:
            handlers = self._subscribers.get(event_type, [])
            if handler in handlers:
                handlers.remove(handler)

    def handlers_for(self, event_type: str) -> List[EventHandler]:
        return list(self._wildcard_subscribers) + list(self._subscribers.get(event_type, []))

    async def emit(self, event: SentinelEvent) -> None:
        handlers = self.handlers_for(event.event_type)
        if not handlers:
            return

        results = await asyncio.gather(
            *[self._safe_dispatch(h, event) for h in handlers],
            return_exceptions=True,
        )

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(
                    "Handler %s failed for event %s: %s",
                    getattr(handlers[i], "__name__", "unknown"),
                    event.event_type,
                    result,
                )

    async def _safe_dispatch(self, handler: EventHandler, event: SentinelEvent) -> None:
        try:
            await handler(event)
        except Exception as exc:
            raise exc
