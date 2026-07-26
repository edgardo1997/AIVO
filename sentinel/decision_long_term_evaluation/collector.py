"""Window lifecycle and aggregate collection engine."""

from datetime import datetime, timezone

from sentinel.decision_shadow_validation.classification import (
    DecisionClassification,
)

from .control import DecisionLongTermControl
from .metrics import DecisionLongTermMetrics
from .window import EvaluationWindowState, EvaluationWindowV1


class LongTermEvaluationEngine:
    def __init__(self, control: DecisionLongTermControl) -> None:
        self.control = control
        self.window: EvaluationWindowV1 | None = None
        self.metrics = DecisionLongTermMetrics()

    def create(
        self,
        *,
        started_at: datetime | None = None,
    ) -> EvaluationWindowV1 | None:
        if not self.control.enabled:
            return None
        if self.window is None:
            self.window = EvaluationWindowV1.create(started_at or datetime.now(timezone.utc))
        return self.window

    def start(self) -> EvaluationWindowV1 | None:
        if self.window is None:
            return None
        if self.window.state is EvaluationWindowState.CREATED:
            self.window = self.window.model_copy(update={"state": EvaluationWindowState.COLLECTING})
        return self.window

    def collect(
        self,
        *,
        classification: DecisionClassification,
        latency_ms: float,
        error: bool = False,
    ) -> bool:
        if not self.control.enabled or self.window is None or self.window.state is not EvaluationWindowState.COLLECTING:
            return False
        try:
            self.metrics.record(
                classification=classification,
                latency_ms=latency_ms,
                error=error,
            )
        except Exception:
            self.metrics.record_loss()
            return False
        return True

    def complete(
        self,
        *,
        ended_at: datetime | None = None,
    ) -> EvaluationWindowV1 | None:
        if self.window is None:
            return None
        if self.window.state is EvaluationWindowState.COLLECTING:
            self.window = self.window.model_copy(
                update={
                    "state": EvaluationWindowState.COMPLETED,
                    "ended_at": ended_at or datetime.now(timezone.utc),
                }
            )
        return self.window
