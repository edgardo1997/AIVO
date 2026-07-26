"""Cryptographic, plan, scope and policy validation."""

from sentinel.contracts import (
    AuthorizationGrantV1,
    AuthorizationStatusV1,
    EvidenceIntegrityStatusV1,
    EvidenceSignalV1,
    ExecutionPlanResultV1,
    PolicyEvaluationResultV1,
)
from sentinel.evidence_integrity import (
    EvidenceVerificationStatus,
    EvidenceVerifier,
)

from .request import SandboxExecutionRequestV1


def execution_validation_errors(
    *,
    request: SandboxExecutionRequestV1,
    plan: ExecutionPlanResultV1,
    grant: AuthorizationGrantV1,
    policy: PolicyEvaluationResultV1,
    evidence: EvidenceSignalV1,
    verifier: EvidenceVerifier,
) -> tuple[str, ...]:
    errors: list[str] = []
    try:
        ExecutionPlanResultV1.model_validate(plan.model_dump())
        AuthorizationGrantV1.model_validate(grant.model_dump())
    except ValueError:
        errors.append("UPSTREAM_CONTRACT_INVALID")
    if request.timestamp >= request.valid_until:
        errors.append("PLAN_EXPIRED")
    if request.timestamp >= grant.expires_at:
        errors.append("AUTHORIZATION_EXPIRED")
    if grant.status is not AuthorizationStatusV1.AUTHORIZED_LIMITED:
        errors.append("AUTHORIZATION_NOT_LIMITED")
    if grant.revoked:
        errors.append("AUTHORIZATION_REVOKED")
    if request.plan_id != plan.plan_id:
        errors.append("PLAN_REFERENCE_MISMATCH")
    if request.authorization_reference != grant.grant_id:
        errors.append("AUTHORIZATION_REFERENCE_MISMATCH")
    if request.policy_reference != policy.policy_id:
        errors.append("POLICY_REFERENCE_MISMATCH")
    if (
        len(
            {
                request.correlation_id,
                plan.correlation_id,
                grant.correlation_id,
                policy.correlation_id,
                evidence.correlation_id,
            }
        )
        != 1
    ):
        errors.append("CORRELATION_MISMATCH")
    if (
        len(
            {
                request.evidence_hash,
                plan.evidence_hash,
                grant.evidence_hash,
                policy.evidence_hash,
                evidence.payload_hash,
            }
        )
        != 1
    ):
        errors.append("EVIDENCE_HASH_MISMATCH")
    if (
        len(
            {
                request.issuer_id,
                plan.issuer_id,
                grant.issuer_id,
                policy.issuer_id,
                evidence.issuer_id,
            }
        )
        != 1
    ):
        errors.append("ISSUER_MISMATCH")
    if request.scope is not grant.scope:
        errors.append("SCOPE_INSUFFICIENT")
    if evidence.integrity_status is not EvidenceIntegrityStatusV1.VERIFIED:
        errors.append("EVIDENCE_NOT_VERIFIED")
    verification = verifier.verify(evidence, now=request.timestamp, detect_replay=False)
    if verification.status is not EvidenceVerificationStatus.VERIFIED:
        errors.append(f"EVIDENCE_{verification.status.value}")
    return tuple(dict.fromkeys(errors))
