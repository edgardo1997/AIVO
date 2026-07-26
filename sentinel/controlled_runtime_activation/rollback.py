"""Logical rollback state without process or runtime side effects."""

from enum import Enum

from .activation import ControlledRuntimeActivation
from .audit import ActivationAudit
from .metrics import ActivationMetrics
from .router import ControlledRuntimeRouter, RuntimeRouteDecisionV1


class RollbackState(str, Enum):
    V2_REQUESTED = "V2_REQUESTED"
    V2_ACCEPTED = "V2_ACCEPTED"
    V2_FAILED = "V2_FAILED"
    ROLLBACK_TO_LEGACY = "ROLLBACK_TO_LEGACY"


class RollbackManager:
    def __init__(
        self,
        *,
        activation: ControlledRuntimeActivation,
        router: ControlledRuntimeRouter,
        metrics: ActivationMetrics,
        audit: ActivationAudit,
    ) -> None:
        self.activation = activation
        self.router = router
        self.metrics = metrics
        self.audit = audit
        self.state = RollbackState.V2_REQUESTED
        self._handled: set[str] = set()

    def mark_accepted(self) -> None:
        self.state = RollbackState.V2_ACCEPTED

    def on_failure(self, request_id: str) -> RuntimeRouteDecisionV1:
        if request_id not in self._handled:
            self._handled.add(request_id)
            self.state = RollbackState.V2_FAILED
            self.metrics.record_failure()
            self.metrics.record_rollback()
            self.activation.activate_rollback()
            self.audit.record("rollback_triggered", "LEGACY")
            self.state = RollbackState.ROLLBACK_TO_LEGACY
        return self.router.force_legacy(request_id)
