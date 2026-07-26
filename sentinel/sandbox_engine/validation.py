"""Grant, gateway, evidence and scope validation."""

from datetime import datetime

from sentinel.contracts import (
    AuthorizationGrantV1,
    AuthorizationStatusV1,
    EvidenceIntegrityStatusV1,
    EvidenceSignalV1,
    SandboxCategoryV1,
    ToolCategoryV1,
    ToolGatewayDecisionResultV1,
    ToolGatewayDecisionValueV1,
)
from sentinel.evidence_integrity import (
    EvidenceVerificationStatus,
    EvidenceVerifier,
)

from .request import SandboxRequestV1

_CATEGORY_COMPATIBILITY = {
    SandboxCategoryV1.FILE_OPERATION: {
        ToolCategoryV1.FILE_READ,
        ToolCategoryV1.FILE_ANALYSIS,
        ToolCategoryV1.USER_APPROVED_CHANGE,
    },
    SandboxCategoryV1.PROCESS_OPERATION: {
        ToolCategoryV1.PROCESS_INFORMATION,
        ToolCategoryV1.USER_APPROVED_CHANGE,
    },
    SandboxCategoryV1.SYSTEM_CONFIGURATION: {
        ToolCategoryV1.SYSTEM_INFORMATION,
        ToolCategoryV1.USER_APPROVED_CHANGE,
    },
    SandboxCategoryV1.APPLICATION_CHANGE: {
        ToolCategoryV1.USER_APPROVED_CHANGE,
    },
    SandboxCategoryV1.DATA_OPERATION: {
        ToolCategoryV1.FILE_ANALYSIS,
        ToolCategoryV1.USER_APPROVED_CHANGE,
    },
}


def validation_errors(
    *,
    request: SandboxRequestV1,
    gateway: ToolGatewayDecisionResultV1,
    grant: AuthorizationGrantV1,
    evidence: EvidenceSignalV1,
    verifier: EvidenceVerifier,
    now: datetime,
) -> tuple[str, ...]:
    errors: list[str] = []
    try:
        AuthorizationGrantV1.model_validate(grant.model_dump())
    except ValueError:
        errors.append("AUTHORIZATION_INTEGRITY_INVALID")
    if grant.status is not AuthorizationStatusV1.AUTHORIZED_LIMITED:
        errors.append("AUTHORIZATION_NOT_LIMITED")
    if grant.revoked:
        errors.append("AUTHORIZATION_REVOKED")
    if now >= grant.expires_at:
        errors.append("AUTHORIZATION_EXPIRED")
    if gateway.decision in {
        ToolGatewayDecisionValueV1.TOOL_BLOCKED,
        ToolGatewayDecisionValueV1.TOOL_UNKNOWN,
    }:
        errors.append("GATEWAY_DECISION_BLOCKS_SIMULATION")
    if request.authorization_reference != grant.grant_id:
        errors.append("AUTHORIZATION_REFERENCE_MISMATCH")
    if gateway.authorization_reference != grant.grant_id:
        errors.append("GATEWAY_AUTHORIZATION_MISMATCH")
    correlation_ids = {
        request.correlation_id,
        gateway.correlation_id,
        grant.correlation_id,
        evidence.correlation_id,
    }
    if len(correlation_ids) != 1:
        errors.append("CORRELATION_MISMATCH")
    evidence_hashes = {
        request.evidence_hash,
        gateway.evidence_hash,
        grant.evidence_hash,
        evidence.payload_hash,
    }
    if len(evidence_hashes) != 1:
        errors.append("EVIDENCE_HASH_MISMATCH")
    issuer_ids = {
        request.issuer_id,
        gateway.issuer_id,
        grant.issuer_id,
        evidence.issuer_id,
    }
    if len(issuer_ids) != 1:
        errors.append("ISSUER_MISMATCH")
    if request.requested_scope is not grant.scope or request.requested_scope is not gateway.scope:
        errors.append("SCOPE_ESCALATION")
    if gateway.requested_tool_category not in _CATEGORY_COMPATIBILITY[request.requested_category]:
        errors.append("CATEGORY_MISMATCH")
    if evidence.integrity_status is not EvidenceIntegrityStatusV1.VERIFIED:
        errors.append("EVIDENCE_NOT_VERIFIED")
    verification = verifier.verify(evidence, now=now, detect_replay=False)
    if verification.status is not EvidenceVerificationStatus.VERIFIED:
        errors.append(f"EVIDENCE_{verification.status.value}")
    return tuple(dict.fromkeys(errors))
