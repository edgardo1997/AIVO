"""Aggregate in-memory metrics without operational payloads."""

from dataclasses import dataclass


@dataclass(frozen=True)
class PersistentControlMetricsSnapshot:
    reservations: int
    transitions: int
    rollbacks: int
    conflicts: int
    recovery_checks: int


class PersistentControlMetrics:
    def __init__(self) -> None:
        self.reservations = 0
        self.transitions = 0
        self.rollbacks = 0
        self.conflicts = 0
        self.recovery_checks = 0

    def snapshot(self) -> PersistentControlMetricsSnapshot:
        return PersistentControlMetricsSnapshot(
            reservations=self.reservations,
            transitions=self.transitions,
            rollbacks=self.rollbacks,
            conflicts=self.conflicts,
            recovery_checks=self.recovery_checks,
        )
