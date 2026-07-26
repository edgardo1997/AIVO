"""Fail-closed planner provenance validation."""

from datetime import datetime

from sentinel.contracts import (
    AuthorizationGrantV1,
    AuthorizationStatusV1,
    EvidenceIntegrityStatusV1,
    EvidenceSignalV1,
    ExecutionBoundaryDecisionResultV1,
    PolicyEvaluationResultV1,
    SandboxSimulationResultV1,
)
from sentinel.evidence_integrity import (
    EvidenceVerificationStatus,
    EvidenceVerifier,
)

from .request import PlannerRequestV1


def planner_validation_errors(
    *,
    request: PlannerRequestV1,
    boundary: ExecutionBoundaryDecisionResultV1,
    grant: AuthorizationGrantV1,
    sandbox: SandboxSimulationResultV1,
    policy: PolicyEvaluationResultV1,
    evidence: EvidenceSignalV1,
    verifier: EvidenceVerifier,
    now: datetime,
) -> tuple[str, ...]:
    errors: list[str] = []
    try:
        AuthorizationGrantV1.model_validate(grant.model_dump())
        ExecutionBoundaryDecisionResultV1.model_validate(boundary.model_dump())
    except ValueError:
        errors.append("UPSTREAM_CONTRACT_INVALID")
    if grant.status is not AuthorizationStatusV1.AUTHORIZED_LIMITED:
        errors.append("AUTHORIZATION_NOT_LIMITED")
    if grant.revoked:
        errors.append("AUTHORIZATION_REVOKED")
    if now >= grant.expires_at:
        errors.append("AUTHORIZATION_EXPIRED")
    if request.authorization_reference != grant.grant_id:
        errors.append("AUTHORIZATION_REFERENCE_MISMATCH")
    if request.boundary_reference != boundary.decision_id:
        errors.append("BOUNDARY_REFERENCE_MISMATCH")
    if request.simulation_reference != sandbox.simulation_id:
        errors.append("SIMULATION_REFERENCE_MISMATCH")
    if request.policy_reference != policy.policy_id:
        errors.append("POLICY_REFERENCE_MISMATCH")
    if (
        len(
            {
                request.correlation_id,
                boundary.correlation_id,
                grant.correlation_id,
                sandbox.correlation_id,
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
                boundary.evidence_hash,
                grant.evidence_hash,
                sandbox.evidence_hash,
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
                boundary.issuer_id,
                grant.issuer_id,
                sandbox.issuer_id,
                policy.issuer_id,
                evidence.issuer_id,
            }
        )
        != 1
    ):
        errors.append("ISSUER_MISMATCH")
    if not (
        request.scope is grant.scope and request.scope is boundary.scope and request.scope is sandbox.affected_scope
    ):
        errors.append("SCOPE_ESCALATION")
    if not (
        request.action_category is boundary.action_category and request.action_category is sandbox.requested_category
    ):
        errors.append("CATEGORY_MISMATCH")
    if evidence.integrity_status is not EvidenceIntegrityStatusV1.VERIFIED:
        errors.append("EVIDENCE_NOT_VERIFIED")
    verification = verifier.verify(evidence, now=now, detect_replay=False)
    if verification.status is not EvidenceVerificationStatus.VERIFIED:
        errors.append(f"EVIDENCE_{verification.status.value}")
    return tuple(dict.fromkeys(errors))
