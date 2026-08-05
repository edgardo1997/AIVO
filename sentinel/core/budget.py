"""Atomic budget reservation for provider/model execution."""

from __future__ import annotations

import threading
from typing import Dict, Optional


class BudgetManager:
    """Thread-safe in-memory budget reservation manager.

    Tracks estimated, reserved, actual, and released cost per provider/model.
    """

    def __init__(self, limits: Optional[Dict[str, float]] = None):
        self._limits: Dict[str, float] = limits or {}
        self._reserved: Dict[str, float] = {}
        self._actual: Dict[str, float] = {}
        self._lock = threading.RLock()

    def set_limit(self, scope: str, amount: float) -> None:
        with self._lock:
            self._limits[scope] = max(0.0, amount)

    def _key(self, provider: str, model: str) -> str:
        return f"{provider}:{model}"

    def reserve(self, provider: str, model: str, estimate: float) -> bool:
        """Atomically reserve estimated cost if the budget allows it."""
        key = self._key(provider, model)
        with self._lock:
            limit = self._limits.get(key, float("inf"))
            if self._reserved.get(key, 0.0) + self._actual.get(key, 0.0) + estimate > limit:
                return False
            self._reserved[key] = self._reserved.get(key, 0.0) + estimate
            return True

    def release(self, provider: str, model: str, estimate: float) -> None:
        """Release a previously reserved estimate (e.g., when the provider is not selected)."""
        key = self._key(provider, model)
        with self._lock:
            self._reserved[key] = max(0.0, self._reserved.get(key, 0.0) - estimate)

    def reconcile(self, provider: str, model: str, estimate: float, actual: float) -> None:
        """Replace an estimated reservation with the actual recorded cost."""
        key = self._key(provider, model)
        with self._lock:
            self._reserved[key] = max(0.0, self._reserved.get(key, 0.0) - estimate)
            self._actual[key] = self._actual.get(key, 0.0) + actual

    def remaining(self, provider: str, model: str) -> float:
        key = self._key(provider, model)
        with self._lock:
            limit = self._limits.get(key, float("inf"))
            used = self._reserved.get(key, 0.0) + self._actual.get(key, 0.0)
            return max(0.0, limit - used)

    def snapshot(self) -> Dict[str, Dict[str, float]]:
        with self._lock:
            return {
                "reserved": dict(self._reserved),
                "actual": dict(self._actual),
                "limits": dict(self._limits),
            }
