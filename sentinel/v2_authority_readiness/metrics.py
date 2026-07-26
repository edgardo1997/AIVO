"""Aggregate metrics for readiness validation runs."""

from dataclasses import dataclass
from threading import RLock

from .gates import GateResult
from .readiness import AuthorityReadinessState


@dataclass(frozen=True)
class AuthorityReadinessMetricsSnapshot:
    validation_runs: int
    approved_runs: int
    blocked_runs: int
    gates_passed: int
    gates_failed: int
    errors: int


class AuthorityReadinessMetrics:
    def __init__(self) -> None:
        self._lock = RLock()
        self._runs = 0
        self._approved = 0
        self._blocked = 0
        self._passed = 0
        self._failed = 0
        self._errors = 0

    def record(
        self,
        *,
        state: AuthorityReadinessState,
        gates: tuple[GateResult, ...],
        error: bool = False,
    ) -> None:
        with self._lock:
            self._runs += 1
            self._approved += int(state is AuthorityReadinessState.HIGH_CONFIDENCE_REVIEW)
            self._blocked += int(state is AuthorityReadinessState.BLOCKED)
            self._passed += sum(gate.passed for gate in gates)
            self._failed += sum(not gate.passed for gate in gates)
            self._errors += int(error)

    def snapshot(self) -> AuthorityReadinessMetricsSnapshot:
        with self._lock:
            return AuthorityReadinessMetricsSnapshot(
                validation_runs=self._runs,
                approved_runs=self._approved,
                blocked_runs=self._blocked,
                gates_passed=self._passed,
                gates_failed=self._failed,
                errors=self._errors,
            )
