"""Operational health vocabulary and evaluator."""

from sentinel.contracts import HealthStateV1

from .incident import IncidentClassification

OperationalHealthStatus = HealthStateV1


class OperationalHealthEvaluator:
    def evaluate(
        self,
        incident: IncidentClassification,
        *,
        total_events: int,
    ) -> OperationalHealthStatus:
        if incident is IncidentClassification.INCIDENT_ROLLBACK_REQUIRED:
            return OperationalHealthStatus.CRITICAL
        if incident is IncidentClassification.INCIDENT_CRITICAL:
            return OperationalHealthStatus.DEGRADED
        if incident is IncidentClassification.INCIDENT_WARNING:
            return OperationalHealthStatus.WARNING
        if total_events == 0:
            return OperationalHealthStatus.OBSERVING
        return OperationalHealthStatus.HEALTHY
