"""Cryptographic and provenance validation for authorization requests."""

from sentinel.contracts import (
    ConsentDecisionResultV1,
    ConsentDecisionValueV1,
    EvidenceIntegrityStatusV1,
    EvidenceSignalV1,
    PolicyEvaluationResultV1,
)
from sentinel.evidence_integrity import (
    EvidenceVerificationStatus,
    EvidenceVerifier,
)

from .policy import policy_allows_evaluation


class AuthorizationValidationError(ValueError):
    pass


def validate_authorization_inputs(
    *,
    consent: ConsentDecisionResultV1,
    policy: PolicyEvaluationResultV1,
    evidence: EvidenceSignalV1,
    verifier: EvidenceVerifier,
) -> None:
    if consent.decision is not ConsentDecisionValueV1.CONSENT_GRANTED:
        raise AuthorizationValidationError("authorization requires granted human consent")
    if consent.revoked:
        raise AuthorizationValidationError("consent has been revoked")
    if not policy_allows_evaluation(policy):
        raise AuthorizationValidationError("blocked policy rejects authorization evaluation")
    if len({consent.correlation_id, policy.correlation_id, evidence.correlation_id}) != 1:
        raise AuthorizationValidationError("authorization correlation mismatch")
    if len({consent.evidence_hash, policy.evidence_hash, evidence.payload_hash}) != 1:
        raise AuthorizationValidationError("authorization evidence mismatch")
    if len({consent.issuer_id, policy.issuer_id, evidence.issuer_id}) != 1:
        raise AuthorizationValidationError("authorization issuer mismatch")
    if evidence.integrity_status is not EvidenceIntegrityStatusV1.VERIFIED:
        raise AuthorizationValidationError("authorization evidence is not verified")
    verification = verifier.verify(evidence, detect_replay=False)
    if verification.status is not EvidenceVerificationStatus.VERIFIED:
        raise AuthorizationValidationError(f"authorization signature rejected: {verification.status.value}")
