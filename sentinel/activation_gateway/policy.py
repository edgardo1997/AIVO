"""Sanitized evidence contract and deterministic eligibility policy."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from .decision import SelectedAuthority

Code = Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]{0,63}$")]
Scope = Annotated[str, Field(pattern=r"^[A-Za-z0-9_.]{1,64}$")]


class RuntimeContextV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    identity_valid: bool
    policy_context_valid: bool
    rollback_available: bool


class GatewayEvidenceV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    request_id: str = Field(pattern=r"^[A-Za-z0-9_.:-]{1,128}$")
    runtime_context: RuntimeContextV1
    readiness_status: Code
    migration_status: Code
    equivalence_status: Code
    safety_status: Code
    scope: tuple[Scope, ...]
    risk_level: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]


class ActivationSelectionPolicy:
    def evaluate(
        self,
        evidence: GatewayEvidenceV1,
        *,
        v2_allowed: bool,
    ) -> tuple[SelectedAuthority, tuple[str, ...], tuple[str, ...]]:
        summary = (
            f"READINESS_{evidence.readiness_status}",
            f"MIGRATION_{evidence.migration_status}",
            f"EQUIVALENCE_{evidence.equivalence_status}",
            f"SAFETY_{evidence.safety_status}",
        )
        if not v2_allowed:
            return (
                SelectedAuthority.LEGACY_ONLY,
                ("V2_ACTIVATION_NOT_ALLOWED",),
                summary,
            )
        blocked = []
        if evidence.equivalence_status == "CRITICAL_DIVERGENCE":
            blocked.append("CRITICAL_DIVERGENCE")
        if evidence.safety_status not in {"HEALTHY", "SAFE_RECOVERY"}:
            blocked.append("SAFETY_NOT_HEALTHY")
        if not evidence.runtime_context.identity_valid:
            blocked.append("IDENTITY_INVALID")
        if not evidence.runtime_context.policy_context_valid:
            blocked.append("POLICY_CONTEXT_INVALID")
        if not evidence.runtime_context.rollback_available:
            blocked.append("ROLLBACK_UNAVAILABLE")
        if evidence.risk_level == "CRITICAL":
            blocked.append("CRITICAL_RISK")
        if blocked:
            return SelectedAuthority.BLOCKED, tuple(blocked), summary
        unavailable = []
        if evidence.readiness_status != "APPROVED_FOR_MIGRATION":
            unavailable.append("READINESS_NOT_APPROVED")
        if evidence.migration_status not in {"SHADOW_ONLY", "LIMITED_CANARY"}:
            unavailable.append("MIGRATION_POLICY_INVALID")
        if evidence.equivalence_status != "EQUIVALENT":
            unavailable.append("EQUIVALENCE_NOT_CONFIRMED")
        if not evidence.scope:
            unavailable.append("SCOPE_INVALID")
        if unavailable:
            return SelectedAuthority.LEGACY_ONLY, tuple(unavailable), summary
        selected = (
            SelectedAuthority.V2_ELIGIBLE_CANARY
            if evidence.migration_status == "LIMITED_CANARY"
            else SelectedAuthority.V2_ELIGIBLE_SHADOW
        )
        return selected, ("ALL_GATES_APPROVED",), summary
