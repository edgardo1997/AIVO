"""Sanitized aggregate signals from isolated V2 validation layers."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ConsolidatedSignalsV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    authority_readiness_status: Literal[
        "BLOCKED",
        "NOT_READY",
        "READY_FOR_REVIEW",
        "APPROVED_FOR_MIGRATION",
    ]
    safety_healthy: bool
    recovery_status: Literal[
        "SAFE_RECOVERY",
        "RECOVERY_OK",
        "RECOVERY_REQUIRED",
        "BLOCKED_RECOVERY",
        "RECOVERY_BLOCKED",
    ]
    state_corrupted: bool
    evidence_available: bool
    evidence_integrity_valid: bool
    critical_data_loss: int = Field(ge=0)
    runtime_equivalence_rate: float = Field(ge=0, le=1)
    critical_divergences: int = Field(ge=0)
    operational_health: Literal[
        "HEALTHY",
        "OBSERVING",
        "WARNING",
        "DEGRADED",
        "CRITICAL",
    ]
    trust_confidence: Literal[
        "UNKNOWN",
        "LOW_CONFIDENCE",
        "MODERATE_CONFIDENCE",
        "HIGH_CONFIDENCE",
        "TRUST_READY_REVIEW",
    ]
    trust_score: float | None = Field(default=None, ge=0, le=100)
    trust_recommendation: Literal[
        "NO_RECOMMENDATION",
        "CONTINUE_OBSERVATION",
        "EXTEND_CANARY",
        "REQUEST_REVIEW",
        "BLOCK_MIGRATION",
    ]
    controlled_activation_enabled: bool
    v2_canary_enabled: bool
