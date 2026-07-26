"""Aggregate-only promotion validation metrics."""

from dataclasses import dataclass
from threading import RLock

from .report import PromotionReport


@dataclass(frozen=True)
class PromotionMetricsSnapshot:
    validation_count: int
    gates_passed: int
    gates_failed: int
    divergences: int
    errors: int


class PromotionMetrics:
    def __init__(self) -> None:
        self._lock = RLock()
        self._values = {
            "validation_count": 0,
            "gates_passed": 0,
            "gates_failed": 0,
            "divergences": 0,
            "errors": 0,
        }

    def record(
        self,
        report: PromotionReport,
        *,
        divergences: int,
        errors: int,
    ) -> None:
        with self._lock:
            self._values["validation_count"] += 1
            self._values["gates_passed"] += len(report.approved_gates)
            self._values["gates_failed"] += len(report.blocked_gates)
            self._values["divergences"] += max(divergences, 0)
            self._values["errors"] += max(errors, 0)

    def snapshot(self) -> PromotionMetricsSnapshot:
        with self._lock:
            return PromotionMetricsSnapshot(**self._values)
