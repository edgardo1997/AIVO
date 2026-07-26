"""Sanitized observation diagnostics."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class CanaryObservationDiagnostic:
    observation_id: str
    timestamp: datetime
    event_type: str
    component: str
    status: str
    latency_ms: float
    result_code: str
