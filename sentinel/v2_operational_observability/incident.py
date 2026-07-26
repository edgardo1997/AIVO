"""Incident classification over aggregate observation signals."""

from enum import Enum
from typing import Protocol


class IncidentClassification(str, Enum):
    INCIDENT_NONE = "INCIDENT_NONE"
    INCIDENT_WARNING = "INCIDENT_WARNING"
    INCIDENT_CRITICAL = "INCIDENT_CRITICAL"
    INCIDENT_ROLLBACK_REQUIRED = "INCIDENT_ROLLBACK_REQUIRED"


class IncidentSignals(Protocol):
    total_events: int
    errors: int
    critical_divergences: int
    lost_events: int
    state_corrupted: bool
    health_failed: bool
    trial_expired: bool


class IncidentDetector:
    def classify(self, signals: IncidentSignals) -> IncidentClassification:
        if signals.state_corrupted or signals.health_failed or signals.critical_divergences > 0:
            return IncidentClassification.INCIDENT_ROLLBACK_REQUIRED
        if signals.lost_events > 10:
            return IncidentClassification.INCIDENT_CRITICAL
        error_rate = signals.errors / max(signals.total_events, 1)
        if error_rate > 0.1:
            return IncidentClassification.INCIDENT_CRITICAL
        if signals.trial_expired or signals.lost_events or signals.errors:
            return IncidentClassification.INCIDENT_WARNING
        return IncidentClassification.INCIDENT_NONE
