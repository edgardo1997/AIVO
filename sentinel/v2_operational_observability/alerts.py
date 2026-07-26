"""Recommendation-only alerts with no action capability."""

from enum import Enum

from .incident import IncidentClassification


class AlertRecommendation(str, Enum):
    NO_ACTION = "NO_ACTION"
    MONITOR = "MONITOR"
    PAUSE_CANARY = "PAUSE_CANARY"
    TRIGGER_ROLLBACK = "TRIGGER_ROLLBACK"
    BLOCK_FUTURE_ACTIVATION = "BLOCK_FUTURE_ACTIVATION"


class AlertEngine:
    def recommend(
        self,
        incident: IncidentClassification,
        *,
        state_corrupted: bool,
    ) -> AlertRecommendation:
        if state_corrupted:
            return AlertRecommendation.BLOCK_FUTURE_ACTIVATION
        return {
            IncidentClassification.INCIDENT_NONE: (AlertRecommendation.NO_ACTION),
            IncidentClassification.INCIDENT_WARNING: (AlertRecommendation.MONITOR),
            IncidentClassification.INCIDENT_CRITICAL: (AlertRecommendation.PAUSE_CANARY),
            IncidentClassification.INCIDENT_ROLLBACK_REQUIRED: (AlertRecommendation.TRIGGER_ROLLBACK),
        }[incident]
