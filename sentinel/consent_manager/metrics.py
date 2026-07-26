"""Aggregate consent counters."""

from dataclasses import dataclass

from sentinel.contracts import (
    ConsentDecisionValueV1,
    DecisionResultV1,
)


class ConsentMetricSnapshotV1(DecisionResultV1):
    pending: int
    granted: int
    denied: int
    expired: int
    revoked: int


@dataclass
class ConsentMetrics:
    pending: int = 0
    granted: int = 0
    denied: int = 0
    expired: int = 0
    revoked: int = 0

    def record(self, decision: ConsentDecisionValueV1) -> None:
        self.pending += int(decision is ConsentDecisionValueV1.CONSENT_PENDING)
        self.granted += int(decision is ConsentDecisionValueV1.CONSENT_GRANTED)
        self.denied += int(decision is ConsentDecisionValueV1.CONSENT_DENIED)
        self.expired += int(decision is ConsentDecisionValueV1.CONSENT_EXPIRED)
        self.revoked += int(decision is ConsentDecisionValueV1.CONSENT_REVOKED)

    def snapshot(self) -> ConsentMetricSnapshotV1:
        return ConsentMetricSnapshotV1(**vars(self))
