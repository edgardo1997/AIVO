"""Fail-closed authorization and provenance checks."""

from datetime import datetime

from sentinel.contracts import (
    ApplicationDescriptorV1,
    ApplicationInstallStateV1,
    ApplicationVerificationLevelV1,
    AuthorizationGrantV1,
    AuthorizationStatusV1,
    EvidenceIntegrityStatusV1,
    EvidenceSignalV1,
    ToolGatewayDecisionResultV1,
    ToolGatewayDecisionValueV1,
    SimulationActionTypeV1,
)
from sentinel.evidence_integrity import EvidenceVerificationStatus, EvidenceVerifier
from sentinel.tool_gateway.catalog import canonical_parameters_hash

from .models import LimitedExecutionRequestV1, LimitedOperationV1

_TOOL_BY_OPERATION = {
    LimitedOperationV1.SYSTEM_INFORMATION: "sentinel.system.information",
    LimitedOperationV1.FILE_METADATA: "sentinel.file.metadata",
    LimitedOperationV1.APPLICATION_LAUNCH: "sentinel.application.launch",
}
_ACTION_BY_OPERATION = {
    LimitedOperationV1.SYSTEM_INFORMATION: (SimulationActionTypeV1.SYSTEM_INFORMATION),
    LimitedOperationV1.FILE_METADATA: SimulationActionTypeV1.FILE_METADATA,
    LimitedOperationV1.APPLICATION_LAUNCH: (SimulationActionTypeV1.APPLICATION_LAUNCH),
}


def validate_execution(
    *,
    request: LimitedExecutionRequestV1,
    grant: AuthorizationGrantV1,
    gateway: ToolGatewayDecisionResultV1,
    evidence: EvidenceSignalV1,
    verifier: EvidenceVerifier,
    descriptor: ApplicationDescriptorV1 | None,
    now: datetime,
) -> tuple[str, ...]:
    errors: list[str] = []
    try:
        AuthorizationGrantV1.model_validate(grant.model_dump())
    except ValueError:
        errors.append("GRANT_INTEGRITY_INVALID")
    if grant.status is not AuthorizationStatusV1.AUTHORIZED_LIMITED:
        errors.append("GRANT_NOT_AUTHORIZED")
    if grant.revoked or grant.consumed_at is not None:
        errors.append("GRANT_UNUSABLE")
    if now >= grant.expires_at:
        errors.append("GRANT_EXPIRED")
    if gateway.decision is not ToolGatewayDecisionValueV1.TOOL_ALLOWED:
        errors.append("GATEWAY_NOT_ALLOWED")
    expected_tool = _TOOL_BY_OPERATION[request.operation]
    if request.tool_id != expected_tool:
        errors.append("OPERATION_TOOL_MISMATCH")
    if grant.allowed_action is not _ACTION_BY_OPERATION[request.operation]:
        errors.append("AUTHORIZED_ACTION_MISMATCH")
    values = {
        request.correlation_id,
        grant.correlation_id,
        gateway.correlation_id,
        evidence.correlation_id,
    }
    if len(values) != 1:
        errors.append("CORRELATION_MISMATCH")
    hashes = {
        request.evidence_hash,
        grant.evidence_hash,
        gateway.evidence_hash,
        evidence.payload_hash,
    }
    if len(hashes) != 1:
        errors.append("EVIDENCE_HASH_MISMATCH")
    if request.authorization_id != grant.authorization_id or gateway.authorization_reference != grant.grant_id:
        errors.append("AUTHORIZATION_MISMATCH")
    if (
        request.plan_id != grant.plan_id
        or request.plan_id != gateway.plan_id
        or request.step_id != gateway.step_id
        or request.tool_id != gateway.tool_id
        or request.params_hash != gateway.params_hash
    ):
        errors.append("EXECUTION_BINDING_MISMATCH")
    step = next(
        (item for item in grant.authorized_steps if item.step_id == request.step_id),
        None,
    )
    if step is None or step.tool_id != request.tool_id or step.params_hash != request.params_hash:
        errors.append("GRANT_STEP_MISMATCH")
    expected_parameters = {
        LimitedOperationV1.SYSTEM_INFORMATION: {},
        LimitedOperationV1.FILE_METADATA: {
            "resource_id": request.resource_id or "",
        },
        LimitedOperationV1.APPLICATION_LAUNCH: {
            "application_id": request.application_id or "",
        },
    }[request.operation]
    if canonical_parameters_hash(expected_parameters) != request.params_hash:
        errors.append("REQUEST_PARAMETER_HASH_MISMATCH")
    if evidence.integrity_status is not EvidenceIntegrityStatusV1.VERIFIED:
        errors.append("EVIDENCE_NOT_VERIFIED")
    verification = verifier.verify(evidence, now=now, detect_replay=False)
    if verification.status is not EvidenceVerificationStatus.VERIFIED:
        errors.append(f"EVIDENCE_{verification.status.value}")
    errors.extend(_descriptor_errors(request, descriptor))
    return tuple(dict.fromkeys(errors))


def _descriptor_errors(
    request: LimitedExecutionRequestV1,
    descriptor: ApplicationDescriptorV1 | None,
) -> tuple[str, ...]:
    if request.operation is not LimitedOperationV1.APPLICATION_LAUNCH:
        return () if descriptor is None else ("UNEXPECTED_APPLICATION_DESCRIPTOR",)
    if descriptor is None:
        return ("APPLICATION_DESCRIPTOR_REQUIRED",)
    errors: list[str] = []
    if request.application_id != descriptor.application_id:
        errors.append("APPLICATION_ID_MISMATCH")
    if descriptor.install_state is not ApplicationInstallStateV1.INSTALLED:
        errors.append("APPLICATION_NOT_INSTALLED")
    if descriptor.verification_level is not ApplicationVerificationLevelV1.VERIFIED or not all(
        item.verified for item in descriptor.resolver_evidence
    ):
        errors.append("APPLICATION_NOT_VERIFIED")
    try:
        ApplicationDescriptorV1.model_validate(descriptor.model_dump())
    except ValueError:
        errors.append("APPLICATION_DESCRIPTOR_INVALID")
    return tuple(errors)
