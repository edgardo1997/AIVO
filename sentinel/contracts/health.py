"""Central V2 health status contract."""

from enum import Enum

from .authority import NonAuthoritativeDecisionV1


class HealthStateV1(str, Enum):
    HEALTHY = "HEALTHY"
    OBSERVING = "OBSERVING"
    WARNING = "WARNING"
    DEGRADED = "DEGRADED"
    CRITICAL = "CRITICAL"


class HealthStatusV1(NonAuthoritativeDecisionV1):
    """Immutable health observation without control-plane authority."""

    state: HealthStateV1
