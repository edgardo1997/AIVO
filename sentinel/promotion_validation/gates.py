"""Independent promotion gates over sanitized evidence."""

import ast
from dataclasses import dataclass
from pathlib import Path

from .promotion_plan import PromotionPlanV1


_REQUIRED_CONTRACTS = {
    "IntentV2",
    "ExecutionPlanV2",
    "PolicyDecisionV2Strict",
    "AuthorizationGrantV1",
    "ApplicationDescriptorV1",
}


@dataclass(frozen=True)
class PromotionEvidence:
    available_contracts: frozenset[str]
    contract_versions: dict[str, str]
    compatibility_validated: bool
    information_loss_detected: bool
    available_dependencies: frozenset[str]
    shadow_observations: int
    minimum_shadow_observations: int
    divergences_total: int
    divergences_classified: bool
    critical_errors: int
    identity_present: bool
    policy_context_valid: bool
    authorization_canary_valid: bool
    replay_detected: bool
    stability_status: str
    error_rate: float
    error_rate_limit: float
    max_latency_ms: float
    latency_limit_ms: float
    boundary_clean: bool
    approvals: frozenset[str] = frozenset()
    approval_rejected: bool = False


@dataclass(frozen=True)
class GateResult:
    gate: str
    passed: bool
    reasons: tuple[str, ...] = ()


class ContractGate:
    name = "contract"

    def evaluate(
        self,
        plan: PromotionPlanV1,
        evidence: PromotionEvidence,
    ) -> GateResult:
        reasons = [f"missing_contract:{name}" for name in sorted(_REQUIRED_CONTRACTS - evidence.available_contracts)]
        if not evidence.compatibility_validated:
            reasons.append("compatibility_not_validated")
        if evidence.information_loss_detected:
            reasons.append("information_loss_detected")
        missing_dependencies = set(plan.required_dependencies) - evidence.available_dependencies
        reasons.extend(f"missing_dependency:{name}" for name in sorted(missing_dependencies))
        return GateResult(self.name, not reasons, tuple(reasons))


class ShadowGate:
    name = "shadow"

    def evaluate(
        self,
        _plan: PromotionPlanV1,
        evidence: PromotionEvidence,
    ) -> GateResult:
        reasons = []
        if evidence.shadow_observations < evidence.minimum_shadow_observations:
            reasons.append("insufficient_shadow_observations")
        if not evidence.divergences_classified:
            reasons.append("unclassified_divergences")
        if evidence.critical_errors:
            reasons.append("critical_shadow_errors")
        return GateResult(self.name, not reasons, tuple(reasons))


class SecurityGate:
    name = "security"

    def evaluate(
        self,
        _plan: PromotionPlanV1,
        evidence: PromotionEvidence,
    ) -> GateResult:
        reasons = []
        if not evidence.identity_present:
            reasons.append("missing_identity")
        if not evidence.policy_context_valid:
            reasons.append("invalid_policy_context")
        if not evidence.authorization_canary_valid:
            reasons.append("invalid_authorization_canary")
        if evidence.replay_detected:
            reasons.append("replay_detected")
        return GateResult(self.name, not reasons, tuple(reasons))


class StabilityGate:
    name = "stability"

    def evaluate(
        self,
        _plan: PromotionPlanV1,
        evidence: PromotionEvidence,
    ) -> GateResult:
        reasons = []
        if evidence.stability_status.upper() != "HEALTHY":
            reasons.append("stability_not_healthy")
        if evidence.error_rate > evidence.error_rate_limit:
            reasons.append("error_rate_above_limit")
        if evidence.max_latency_ms > evidence.latency_limit_ms:
            reasons.append("latency_above_limit")
        return GateResult(self.name, not reasons, tuple(reasons))


class BoundaryGate:
    name = "boundary"

    _FORBIDDEN_IMPORTS = {
        "sentinel.core.planner",
        "sentinel.core.policy_engine",
        "sentinel.core.decision_engine",
        "sentinel.core.tool_gateway",
        "sentinel.core.orchestrator",
        "sidecar.services.executor_service",
        "subprocess",
    }
    _FORBIDDEN_CALLS = {
        "execute",
        "launch",
        "run",
        "popen",
        "system",
        "AuthorizationGrantV1",
    }

    def evaluate(
        self,
        _plan: PromotionPlanV1,
        evidence: PromotionEvidence,
    ) -> GateResult:
        reasons = []
        if not evidence.boundary_clean:
            reasons.append("external_boundary_check_failed")
        reasons.extend(self._scan())
        return GateResult(self.name, not reasons, tuple(reasons))

    def _scan(self) -> list[str]:
        violations: list[str] = []
        module_dir = Path(__file__).resolve().parent
        for path in module_dir.glob("*.py"):
            tree = ast.parse(
                path.read_text(encoding="utf-8"),
                filename=str(path),
            )
            for node in ast.walk(tree):
                modules = ()
                if isinstance(node, ast.Import):
                    modules = tuple(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    modules = (node.module,)
                for module in modules:
                    if any(
                        module == forbidden or module.startswith(f"{forbidden}.")
                        for forbidden in self._FORBIDDEN_IMPORTS
                    ):
                        violations.append("forbidden_runtime_import")
                if isinstance(node, ast.Call):
                    called = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
                    if called.casefold() in {item.casefold() for item in self._FORBIDDEN_CALLS}:
                        violations.append("forbidden_execution_call")
        return list(dict.fromkeys(violations))
