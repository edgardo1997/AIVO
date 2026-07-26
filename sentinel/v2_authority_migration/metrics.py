"""Aggregate migration routing metrics."""

from dataclasses import dataclass
from threading import RLock

from .router import AuthoritySelection


@dataclass(frozen=True)
class AuthorityMigrationMetricsSnapshot:
    routing_decisions: int
    legacy_selections: int
    v2_selections: int
    fallbacks: int
    rollbacks: int


class AuthorityMigrationMetrics:
    def __init__(self) -> None:
        self._lock = RLock()
        self._routing = 0
        self._legacy = 0
        self._v2 = 0
        self._fallbacks = 0
        self._rollbacks = 0

    def record(self, selection: AuthoritySelection) -> None:
        with self._lock:
            self._routing += 1
            self._legacy += int(selection is AuthoritySelection.LEGACY_AUTHORITY)
            self._v2 += int(selection is AuthoritySelection.V2_AUTHORITY)
            self._fallbacks += int(selection is AuthoritySelection.FALLBACK_LEGACY)

    def record_rollback(self) -> None:
        with self._lock:
            self._rollbacks += 1

    def snapshot(self) -> AuthorityMigrationMetricsSnapshot:
        with self._lock:
            return AuthorityMigrationMetricsSnapshot(
                routing_decisions=self._routing,
                legacy_selections=self._legacy,
                v2_selections=self._v2,
                fallbacks=self._fallbacks,
                rollbacks=self._rollbacks,
            )
