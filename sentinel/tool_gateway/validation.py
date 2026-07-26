"""Origin validation over central contracts only."""

from datetime import datetime

from sentinel.contracts import (
    AuthorizationGrantV1,
    AuthorizationStatusV1,
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

from .request import ToolRequestV1
from .catalog import VerifiedToolCatalog, canonical_parameters_hash


def origin_violations(
    *,
    request: ToolRequestV1,
    grant: AuthorizationGrantV1,
    consent: ConsentDecisionResultV1,
    evidence: EvidenceSignalV1,
    policy: PolicyEvaluationResultV1,
    verifier: EvidenceVerifier,
    now: datetime,
) -> tuple[str, ...]:
    violations: list[str] = []
    try:
        AuthorizationGrantV1.model_validate(grant.model_dump())
    except ValueError:
        violations.append("AUTHORIZATION_INTEGRITY_INVALID")
    if grant.status is not AuthorizationStatusV1.AUTHORIZED_LIMITED:
        violations.append("AUTHORIZATION_NOT_LIMITED")
    if grant.revoked:
        violations.append("AUTHORIZATION_REVOKED")
    if now >= grant.expires_at:
        violations.append("AUTHORIZATION_EXPIRED")
    if consent.decision is not ConsentDecisionValueV1.CONSENT_GRANTED or consent.revoked:
        violations.append("CONSENT_NOT_GRANTED")
    if now >= consent.expiration_time:
        violations.append("CONSENT_EXPIRED")
    correlation_ids = {
        request.correlation_id,
        grant.correlation_id,
        consent.correlation_id,
        evidence.correlation_id,
        policy.correlation_id,
    }
    if len(correlation_ids) != 1:
        violations.append("CORRELATION_MISMATCH")
    evidence_hashes = {
        request.evidence_hash,
        grant.evidence_hash,
        consent.evidence_hash,
        evidence.payload_hash,
        policy.evidence_hash,
    }
    if len(evidence_hashes) != 1:
        violations.append("EVIDENCE_HASH_MISMATCH")
    issuer_ids = {
        request.issuer_id,
        grant.issuer_id,
        consent.issuer_id,
        evidence.issuer_id,
        policy.issuer_id,
    }
    if len(issuer_ids) != 1:
        violations.append("ISSUER_MISMATCH")
    if request.authorization_reference != grant.grant_id:
        violations.append("AUTHORIZATION_REFERENCE_MISMATCH")
    if request.plan_id != grant.plan_id:
        violations.append("PLAN_MISMATCH")
    matching_steps = tuple(step for step in grant.authorized_steps if step.step_id == request.step_id)
    if not matching_steps:
        violations.append("STEP_NOT_AUTHORIZED")
    elif matching_steps[0].tool_id != request.tool_id or matching_steps[0].params_hash != request.params_hash:
        violations.append("GRANT_BINDING_MISMATCH")
    if grant.consumed_at is not None:
        violations.append("AUTHORIZATION_REPLAYED")
    if request.params_hash is not None and request.params_hash != grant.params_hash:
        violations.append("PARAMETER_HASH_MISMATCH")
    if policy.action_type != grant.allowed_action:
        violations.append("ACTION_MISMATCH")
    if evidence.integrity_status is not EvidenceIntegrityStatusV1.VERIFIED:
        violations.append("EVIDENCE_NOT_VERIFIED")
    verification = verifier.verify(evidence, now=now, detect_replay=False)
    if verification.status is not EvidenceVerificationStatus.VERIFIED:
        violations.append(f"EVIDENCE_{verification.status.value}")
    return tuple(dict.fromkeys(violations))


def catalog_violations(
    *,
    request: ToolRequestV1,
    catalog: VerifiedToolCatalog,
) -> tuple[str, ...]:
    specification = catalog.resolve(request.tool_id, request.tool_version)
    if specification is None:
        return ("TOOL_NOT_IN_CATALOG",)
    violations: list[str] = []
    if request.requested_tool_category is not specification.category:
        violations.append("TOOL_CATEGORY_MISMATCH")
    if request.requested_scope not in specification.allowed_scopes:
        violations.append("TOOL_SCOPE_MISMATCH")
    violations.extend(
        catalog.validate_parameters(
            specification,
            request.parameter_values(),
        )
    )
    try:
        observed_hash = canonical_parameters_hash(request.parameter_values())
    except ValueError:
        observed_hash = ""
    if observed_hash != request.params_hash:
        violations.append("PARAMETER_HASH_MISMATCH")
    return tuple(dict.fromkeys(violations))
