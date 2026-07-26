"""Pure pre-cutover readiness inspection for isolated contracts."""

import ast
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from sentinel.contracts import (
    AuthorizationGrantV1,
    LaunchReceiptV1,
    PendingConsentV1,
    PolicyContextV1,
    ResolverEvidenceV1,
)

from .observer import ShadowMigrationGapType, ShadowMigrationObserver
from .decision_comparison import ShadowDecisionComparison
from .runtime_adapter import RuntimeShadowAdapter


class CutoverReadinessState(str, Enum):
    READY = "READY"
    BLOCKED = "BLOCKED"
    WARNING = "WARNING"


@dataclass(frozen=True)
class CutoverReadinessReport:
    state: CutoverReadinessState
    checks: dict[str, bool]
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]


class CutoverReadinessValidator:
    """Inspect availability and diagnostics without executing anything."""

    _CONTRACTS = {
        "authorization_grant": AuthorizationGrantV1,
        "pending_consent": PendingConsentV1,
        "policy_context": PolicyContextV1,
        "resolver_evidence": ResolverEvidenceV1,
        "launch_receipt": LaunchReceiptV1,
    }
    _FORBIDDEN_IMPORTS = {
        "sentinel.core.orchestrator",
        "sentinel.core.tool_gateway",
        "sidecar.services.executor_service",
        "sidecar.modules.executor",
    }

    def validate(
        self,
        observer: ShadowMigrationObserver | None = None,
    ) -> CutoverReadinessReport:
        checks = {name: contract is not None for name, contract in self._CONTRACTS.items()}
        checks.update(
            {
                "runtime_shadow_adapter": RuntimeShadowAdapter is not None,
                "shadow_observer": ShadowMigrationObserver is not None,
                "decision_comparison": ShadowDecisionComparison is not None,
            }
        )
        blockers = [f"missing required contract: {name}" for name, passed in checks.items() if not passed]
        violations = self._architecture_violations()
        checks["shadow_architecture_safe"] = not violations
        blockers.extend(violations)
        warnings: list[str] = []
        if observer is not None:
            for result in observer.results():
                if result.conversion_status == "ERROR":
                    blockers.append(f"{result.component} shadow conversion failed")
                elif not result.conversion_success:
                    warnings.append(f"{result.component} shadow conversion incomplete")
                for diagnostic in result.diagnostics:
                    if diagnostic.gap_type is ShadowMigrationGapType.MISSING_CONTRACT:
                        blockers.append(diagnostic.message)
                    elif diagnostic.gap_type in {
                        ShadowMigrationGapType.MISSING_FIELD,
                        ShadowMigrationGapType.WARNING,
                    }:
                        warnings.append(diagnostic.message)
        checks["shadow_observer_no_critical_errors"] = not blockers
        if blockers:
            state = CutoverReadinessState.BLOCKED
        elif warnings:
            state = CutoverReadinessState.WARNING
        else:
            state = CutoverReadinessState.READY
        return CutoverReadinessReport(
            state=state,
            checks=checks,
            blockers=tuple(dict.fromkeys(blockers)),
            warnings=tuple(dict.fromkeys(warnings)),
        )

    def _architecture_violations(self) -> list[str]:
        shadow_dir = Path(__file__).resolve().parent
        violations: list[str] = []
        for source_path in shadow_dir.glob("*.py"):
            tree = ast.parse(
                source_path.read_text(encoding="utf-8"),
                filename=str(source_path),
            )
            for node in ast.walk(tree):
                imported: tuple[str, ...] = ()
                if isinstance(node, ast.Import):
                    imported = tuple(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported = (node.module,)
                for module in imported:
                    if any(
                        module == forbidden or module.startswith(f"{forbidden}.")
                        for forbidden in self._FORBIDDEN_IMPORTS
                    ):
                        violations.append(f"forbidden shadow import in {source_path.name}: {module}")
        return violations
