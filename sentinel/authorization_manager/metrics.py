"""Aggregate authorization lifecycle counters."""

from dataclasses import dataclass

from sentinel.contracts import AuthorizationStatusV1, DecisionResultV1


class AuthorizationMetricSnapshotV1(DecisionResultV1):
    pending: int
    limited: int
    expired: int
    revoked: int
    denied: int


@dataclass
class AuthorizationMetrics:
    pending: int = 0
    limited: int = 0
    expired: int = 0
    revoked: int = 0
    denied: int = 0

    def record(self, status: AuthorizationStatusV1) -> None:
        self.pending += int(status is AuthorizationStatusV1.AUTH_PENDING)
        self.limited += int(status is AuthorizationStatusV1.AUTHORIZED_LIMITED)
        self.expired += int(status is AuthorizationStatusV1.AUTH_EXPIRED)
        self.revoked += int(status is AuthorizationStatusV1.AUTH_REVOKED)
        self.denied += int(status is AuthorizationStatusV1.AUTH_DENIED)

    def snapshot(self) -> AuthorizationMetricSnapshotV1:
        return AuthorizationMetricSnapshotV1(**vars(self))
