"""Identity, provenance, plan and scope validation."""

from sentinel.contracts import (
    AuthorizationGrantV1,
    AuthorizationStatusV1,
    EvidenceIntegrityStatusV1,
    EvidenceSignalV1,
    ExecutionPlanResultV1,
    SandboxExecutionResultV1,
)
from sentinel.evidence_integrity import (
    EvidenceVerificationStatus,
    EvidenceVerifier,
)

from .request import IsolationRequestV1


def isolation_validation_errors(
    *,
    request: IsolationRequestV1,
    execution: SandboxExecutionResultV1,
    plan: ExecutionPlanResultV1,
    grant: AuthorizationGrantV1,
    evidence: EvidenceSignalV1,
    verifier: EvidenceVerifier,
) -> tuple[str, ...]:
    errors: list[str] = []
    try:
        SandboxExecutionResultV1.model_validate(execution.model_dump())
        ExecutionPlanResultV1.model_validate(plan.model_dump())
        AuthorizationGrantV1.model_validate(grant.model_dump())
    except ValueError:
        errors.append("UPSTREAM_CONTRACT_INVALID")
    if grant.status is not AuthorizationStatusV1.AUTHORIZED_LIMITED:
        errors.append("AUTHORIZATION_NOT_LIMITED")
    if grant.revoked:
        errors.append("AUTHORIZATION_REVOKED")
    if request.timestamp >= grant.expires_at:
        errors.append("AUTHORIZATION_EXPIRED")
    if request.execution_reference != execution.execution_id:
        errors.append("EXECUTION_REFERENCE_MISMATCH")
    if request.plan_reference != plan.plan_id or execution.plan_id != plan.plan_id:
        errors.append("PLAN_INCONSISTENT")
    if request.authorization_reference != grant.grant_id:
        errors.append("AUTHORIZATION_REFERENCE_MISMATCH")
    if plan.authorization_reference != grant.grant_id:
        errors.append("PLAN_AUTHORIZATION_MISMATCH")
    if (
        len(
            {
                request.correlation_id,
                execution.correlation_id,
                plan.correlation_id,
                grant.correlation_id,
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
                execution.evidence_hash,
                plan.evidence_hash,
                grant.evidence_hash,
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
                execution.issuer_id,
                plan.issuer_id,
                grant.issuer_id,
                evidence.issuer_id,
            }
        )
        != 1
    ):
        errors.append("IDENTITY_OR_ISSUER_UNKNOWN")
    if request.requested_scope is not grant.scope:
        errors.append("SCOPE_ESCALATION")
    if evidence.integrity_status is not EvidenceIntegrityStatusV1.VERIFIED:
        errors.append("EVIDENCE_NOT_VERIFIED")
    verification = verifier.verify(evidence, now=request.timestamp, detect_replay=False)
    if verification.status is not EvidenceVerificationStatus.VERIFIED:
        errors.append(f"EVIDENCE_{verification.status.value}")
    return tuple(dict.fromkeys(errors))
