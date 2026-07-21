"""Centralized event type registry.

Ensures all components use consistent event type names.
"""

from typing import Set, Optional

from sentinel.core.event_types import ALL_EVENTS, PIPELINE_STARTED


class EventRegistry:
    def __init__(self, valid_events: Optional[Set[str]] = None):
        self._valid = valid_events or set(ALL_EVENTS)

    @property
    def valid_events(self) -> Set[str]:
        return set(self._valid)

    def is_valid(self, event_type: str) -> bool:
        return event_type in self._valid or event_type == "*"

    def validate(self, event_type: str) -> None:
        if not self.is_valid(event_type):
            valid_list = ", ".join(sorted(self._valid))
            raise ValueError(
                f"Unknown event type: '{event_type}'. "
                f"Valid types: {valid_list}"
            )

    def register(self, event_type: str) -> None:
        self._valid.add(event_type)

    def register_many(self, event_types: Set[str]) -> None:
        self._valid.update(event_types)
