"""Sanitized immutable contracts for Legacy/V2 shadow comparison."""

from datetime import datetime
from enum import Enum
from typing import Annotated

from pydantic import AfterValidator, Field

from sentinel.contracts import (
    AuthorizationScopeV1,
    DecisionResultV1,
)
from sentinel.contracts._base import require_timezone
from sentinel.v2_unified_pipeline import UnifiedPipelineResultV1

AwareDatetime = Annotated[datetime, AfterValidator(require_timezone)]
HashValue = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
SafeIdentifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9_.:-]{1,128}$")]
SafeCode = Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]{0,63}$")]


class DivergenceSeverityV1(str, Enum):
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class DivergenceClassificationV1(str, Enum):
    MATCH = "MATCH"
    EXPECTED_DIFFERENCE = "EXPECTED_DIFFERENCE"
    INFORMATION_LOSS = "INFORMATION_LOSS"
    SECURITY_IMPROVEMENT = "SECURITY_IMPROVEMENT"
    V2_REGRESSION = "V2_REGRESSION"
    CRITICAL_DIVERGENCE = "CRITICAL_DIVERGENCE"


class LegacyRuntimeSnapshotV1(DecisionResultV1):
    """Payload-free copy emitted after a Legacy decision."""

    snapshot_id: SafeIdentifier
    correlation_id: SafeIdentifier
    timestamp: AwareDatetime
    plan_fingerprint: HashValue
    policy_decision: SafeCode
    scope: AuthorizationScopeV1
    result_code: SafeCode
    lost_fields: tuple[SafeCode, ...] = ()


class ShadowDivergenceV1(DecisionResultV1):
    field: SafeCode
    classification: DivergenceClassificationV1
    severity: DivergenceSeverityV1
    legacy_value: SafeCode
    v2_value: SafeCode
    reason: SafeCode


class ShadowComparisonResultV1(DecisionResultV1):
    comparison_id: SafeIdentifier
    correlation_id: SafeIdentifier
    evidence_hash: HashValue
    timestamp: AwareDatetime
    divergences: tuple[ShadowDivergenceV1, ...]
    critical_count: int = Field(ge=0)
    information_loss_count: int = Field(ge=0)
    matched: bool


class ShadowRuntimeObservationResultV1(DecisionResultV1):
    observation_id: SafeIdentifier
    correlation_id: SafeIdentifier
    evidence_hash: HashValue
    timestamp: AwareDatetime
    observed: bool
    pipeline_result: UnifiedPipelineResultV1 | None = None
    comparison: ShadowComparisonResultV1 | None = None
    warnings: tuple[SafeCode, ...] = ()
    error_code: SafeCode | None = None
