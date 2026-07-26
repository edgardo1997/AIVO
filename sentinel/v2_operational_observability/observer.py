"""Aggregate observer that produces recommendations, never actions."""

from pydantic import BaseModel, ConfigDict, Field

from sentinel.contracts import DecisionResultV1

from .alerts import AlertEngine, AlertRecommendation
from .control import V2OperationalObservabilityControl
from .health import OperationalHealthEvaluator, OperationalHealthStatus
from .incident import IncidentClassification, IncidentDetector
from .metrics import OperationalMetrics
from .timeline import OperationalTimeline


class ObservationBatchV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    correlation_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    legacy_decisions: int = Field(ge=0)
    v2_decisions: int = Field(ge=0)
    canary_active: bool
    rollback_events: int = Field(ge=0)
    total_events: int = Field(ge=0)
    errors: int = Field(ge=0)
    divergences: int = Field(ge=0)
    critical_divergences: int = Field(ge=0)
    lost_events: int = Field(ge=0)
    average_latency_ms: float = Field(ge=0)
    stable: bool
    state_corrupted: bool
    health_failed: bool
    trial_expired: bool
    canary_duration_seconds: float = Field(ge=0)


class ObservationResultV1(DecisionResultV1):
    incident: IncidentClassification
    recommendation: AlertRecommendation
    health: OperationalHealthStatus


class OperationalObserver:
    def __init__(
        self,
        *,
        control: V2OperationalObservabilityControl,
        metrics: OperationalMetrics | None = None,
        timeline: OperationalTimeline | None = None,
    ) -> None:
        self.control = control
        self.metrics = metrics or OperationalMetrics()
        self.timeline = timeline if control.enabled else None
        if self.timeline is None and control.enabled:
            self.timeline = OperationalTimeline()
        self._incidents = IncidentDetector()
        self._alerts = AlertEngine()
        self._health = OperationalHealthEvaluator()
        self._last_health: OperationalHealthStatus | None = None

    def observe(self, batch: ObservationBatchV1) -> ObservationResultV1 | None:
        if not self.control.enabled:
            return None
        incident = self._incidents.classify(batch)
        recommendation = self._alerts.recommend(
            incident,
            state_corrupted=batch.state_corrupted,
        )
        health = self._health.evaluate(
            incident,
            total_events=batch.total_events,
        )
        changed = self._last_health is not None and health is not self._last_health
        self._last_health = health
        self.metrics.record(
            events=batch.total_events,
            errors=batch.errors,
            divergences=batch.divergences,
            rollbacks=batch.rollback_events,
            canary_duration_seconds=batch.canary_duration_seconds,
            health_changed=changed,
            incident=incident is not IncidentClassification.INCIDENT_NONE,
        )
        event = _event_for(batch, incident)
        self.timeline.append(
            event_type=event,
            correlation_hash=batch.correlation_hash,
            sanitized_result=incident.value,
        )
        return ObservationResultV1(
            incident=incident,
            recommendation=recommendation,
            health=health,
        )


def _event_for(
    batch: ObservationBatchV1,
    incident: IncidentClassification,
) -> str:
    if batch.rollback_events:
        return "rollback_triggered"
    if batch.critical_divergences or batch.divergences:
        return "divergence_detected"
    if incident is not IncidentClassification.INCIDENT_NONE:
        return "health_warning"
    if batch.canary_active:
        return "canary_started"
    return "activation_attempt"
