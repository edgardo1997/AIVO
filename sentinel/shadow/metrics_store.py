"""Bounded in-memory persistence for aggregate shadow diagnostics."""

from dataclasses import dataclass
from threading import RLock

from sentinel.contracts import ShadowExecutionTraceV1


@dataclass(frozen=True)
class ShadowMetricSnapshot:
    conversion_success: int
    conversion_failure: int
    schema_gap: int
    decision_difference: int
    missing_identity: int
    missing_context: int


class ShadowMetricsStore:
    """Persist counters only; trace payloads and identities are discarded."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._counts = {
            "conversion_success": 0,
            "conversion_failure": 0,
            "schema_gap": 0,
            "decision_difference": 0,
            "missing_identity": 0,
            "missing_context": 0,
        }

    def record(self, trace: ShadowExecutionTraceV1) -> None:
        with self._lock:
            status_key = (
                "conversion_success" if trace.conversion_status in {"SUCCESS", "WARNING"} else "conversion_failure"
            )
            self._counts[status_key] += 1
            tokens = set(trace.warnings) | set(trace.differences)
            self._counts["schema_gap"] += any("schema_gap" in token or "missing_field" in token for token in tokens)
            self._counts["decision_difference"] += any(
                "decision_changed" in token or "effect_different" in token for token in tokens
            )
            self._counts["missing_identity"] += any("missing_identity" in token for token in tokens)
            self._counts["missing_context"] += any("missing_context" in token for token in tokens)

    def snapshot(self) -> ShadowMetricSnapshot:
        with self._lock:
            return ShadowMetricSnapshot(**self._counts)
