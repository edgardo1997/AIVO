"""Central V2 readiness state contract."""

from enum import Enum

from pydantic import Field

from .authority import NonAuthoritativeDecisionV1
from .decision import DecisionResultV1


class ReadinessStateValueV1(str, Enum):
    BLOCKED = "BLOCKED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    READY_FOR_HUMAN_REVIEW = "READY_FOR_HUMAN_REVIEW"
    HIGH_CONFIDENCE_REVIEW = "HIGH_CONFIDENCE_REVIEW"
    NOT_APPROVED = "NOT_APPROVED"


class ReadinessStateV1(NonAuthoritativeDecisionV1):
    """Immutable readiness classification; never an activation approval."""

    state: ReadinessStateValueV1


class ReadinessResultV1(DecisionResultV1):
    """Evidence-bound readiness result for human review only."""

    status: ReadinessStateValueV1
    confidence: float = Field(ge=0, le=100)
    evidence_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    correlation_id: str = Field(pattern=r"^[A-Za-z0-9_.:-]{1,128}$")
