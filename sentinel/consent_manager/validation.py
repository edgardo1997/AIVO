"""Contract provenance and cryptographic validation."""

from sentinel.contracts import (
    EvidenceIntegrityStatusV1,
    EvidenceSignalV1,
    PolicyEvaluationResultV1,
    ReadinessResultV1,
    SimulationResultV1,
)
from sentinel.evidence_integrity import (
    EvidenceVerificationStatus,
    EvidenceVerifier,
)
from sentinel.recommendation_engine import RecommendationResultV1

from .policy import policy_accepts_consent_request


class ConsentValidationError(ValueError):
    pass


def validate_consent_request(
    *,
    policy: PolicyEvaluationResultV1,
    simulation: SimulationResultV1,
    recommendation: RecommendationResultV1,
    evidence: EvidenceSignalV1,
    readiness: ReadinessResultV1,
    verifier: EvidenceVerifier,
) -> None:
    correlation_ids = {
        policy.correlation_id,
        simulation.correlation_id,
        recommendation.correlation_id,
        evidence.correlation_id,
        readiness.correlation_id,
    }
    evidence_hashes = {
        policy.evidence_hash,
        simulation.evidence_hash,
        recommendation.evidence_hash,
        evidence.payload_hash,
        readiness.evidence_hash,
    }
    issuer_ids = {
        policy.issuer_id,
        simulation.issuer_id,
        recommendation.issuer_id,
        evidence.issuer_id,
    }
    if len(correlation_ids) != 1:
        raise ConsentValidationError("consent correlation mismatch")
    if len(evidence_hashes) != 1:
        raise ConsentValidationError("consent evidence mismatch")
    if len(issuer_ids) != 1:
        raise ConsentValidationError("consent issuer mismatch")
    if evidence.integrity_status is not EvidenceIntegrityStatusV1.VERIFIED:
        raise ConsentValidationError("consent evidence is not verified")
    verification = verifier.verify(evidence, detect_replay=False)
    if verification.status is not EvidenceVerificationStatus.VERIFIED:
        raise ConsentValidationError(f"consent signature rejected: {verification.status.value}")
    if not policy_accepts_consent_request(policy):
        raise ConsentValidationError("policy does not permit consent review")
