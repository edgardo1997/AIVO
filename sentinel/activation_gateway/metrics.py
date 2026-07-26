"""Aggregate-only activation gateway counters."""

from dataclasses import dataclass
from threading import RLock

from .decision import SelectedAuthority


@dataclass(frozen=True)
class ActivationGatewayMetricsSnapshot:
    total_evaluations: int
    legacy_selected: int
    v2_candidate_selected: int
    blocked: int
    fallbacks: int
    errors: int


class ActivationGatewayMetrics:
    def __init__(self) -> None:
        self._lock = RLock()
        self._values = {
            "total_evaluations": 0,
            "legacy_selected": 0,
            "v2_candidate_selected": 0,
            "blocked": 0,
            "fallbacks": 0,
            "errors": 0,
        }

    def record_selection(self, selection: SelectedAuthority) -> None:
        with self._lock:
            self._values["total_evaluations"] += 1
            self._values["legacy_selected"] += int(selection is SelectedAuthority.LEGACY_ONLY)
            self._values["v2_candidate_selected"] += int(
                selection
                in {
                    SelectedAuthority.V2_ELIGIBLE_SHADOW,
                    SelectedAuthority.V2_ELIGIBLE_CANARY,
                }
            )
            self._values["blocked"] += int(selection is SelectedAuthority.BLOCKED)

    def record_fallback(self) -> None:
        with self._lock:
            self._values["fallbacks"] += 1

    def record_error(self) -> None:
        with self._lock:
            self._values["errors"] += 1

    def snapshot(self) -> ActivationGatewayMetricsSnapshot:
        with self._lock:
            return ActivationGatewayMetricsSnapshot(**self._values)
