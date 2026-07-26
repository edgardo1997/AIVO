"""Reproducible confidence consolidation."""

from sentinel.contracts import EvidenceIntegrityStatusV1, ReadinessResultV1
from sentinel.shadow_decision_orchestrator.orchestrator import (
    ShadowDecisionResultV1,
)
from sentinel.v2_trust_evaluation import TrustEvaluationResultV1


def consolidated_confidence(
    *,
    shadow: ShadowDecisionResultV1,
    trust: TrustEvaluationResultV1,
    readiness: ReadinessResultV1,
    integrity: EvidenceIntegrityStatusV1,
) -> float:
    value = round(
        (shadow.comparison.confidence + trust.score + readiness.confidence) / 3,
        2,
    )
    if integrity is EvidenceIntegrityStatusV1.INVALID:
        return 0.0
    if integrity is not EvidenceIntegrityStatusV1.VERIFIED:
        return min(value, 25.0)
    return value
