"""Final evidence validation without authority or runtime integration."""

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sentinel.canary_observation import CanaryHealthStatus
from sentinel.contracts import (
    ApplicationDescriptorV1,
    AuthorizationGrantV1,
    ExecutionPlanV2,
    IntentV2,
    LaunchReceiptV1,
    PolicyDecisionV2Strict,
)

from .classification import ClassifiedDivergence
from .comparison import classify_all
from .control import cutover_validation_enabled
from .metrics import CutoverHistoricalMetrics
from .report import CutoverReadinessReport, CutoverReadinessState


_REQUIRED_CONTRACTS = {
    "IntentV2": IntentV2,
    "ExecutionPlanV2": ExecutionPlanV2,
    "PolicyDecisionV2Strict": PolicyDecisionV2Strict,
    "AuthorizationGrantV1": AuthorizationGrantV1,
    "ApplicationDescriptorV1": ApplicationDescriptorV1,
    "LaunchReceiptV1": LaunchReceiptV1,
}


@dataclass(frozen=True)
class CutoverValidationInput:
    runtime_canary_metrics: dict[str, int | float]
    observation_metrics: dict[str, int | float]
    policy_shadow_metrics: dict[str, int | float]
    discovery_metrics: dict[str, int | float]
    authorization_metrics: dict[str, int | float]
    health_status: CanaryHealthStatus
    divergences: tuple[str, ...] = ()
    available_contracts: frozenset[str] = frozenset(_REQUIRED_CONTRACTS)
    shadow_active: bool = True
    canary_active: bool = True
    metrics_available: bool = True
    no_critical_errors: bool = True
    shadow_no_execution: bool = True
    ast_boundaries_clean: bool = True
    no_productive_grants: bool = True
    no_policy_bypass: bool = True
    identity_present: bool = True
    policy_context_present: bool = True
    authorization_consistent: bool = True
    replay_possible: bool = False
    discovery_evidence_present: bool = True


@dataclass(frozen=True)
class CutoverChecklist:
    contracts: dict[str, bool]
    observability: dict[str, bool]
    security: dict[str, bool]

    def as_dict(self) -> dict[str, dict[str, bool]]:
        return {
            "contracts": dict(self.contracts),
            "observability": dict(self.observability),
            "security": dict(self.security),
        }


class CutoverValidationEngine:
    """Classify aggregate evidence; never initiates a cutover."""

    def __init__(
        self,
        *,
        enabled: bool | None = None,
        history: CutoverHistoricalMetrics | None = None,
    ) -> None:
        self._enabled = cutover_validation_enabled() if enabled is None else enabled
        self.history = history or CutoverHistoricalMetrics()

    @property
    def enabled(self) -> bool:
        return self._enabled

    def validate(
        self,
        evidence: CutoverValidationInput,
    ) -> CutoverReadinessReport:
        timestamp = datetime.now(timezone.utc)
        if not self._enabled:
            return CutoverReadinessReport(
                validation_id="cutover_validation_disabled",
                timestamp=timestamp,
                evaluated_components=(),
                overall_state=CutoverReadinessState.BLOCKED,
                metrics_summary=_summarize_metrics(evidence),
                blockers=("cutover_validation_disabled",),
                warnings=(),
                recommendations=("No realizar cutover; habilitar validación explícita.",),
                divergences=(),
                checklist=CutoverChecklist(
                    contracts={},
                    observability={},
                    security={},
                ).as_dict(),
            )

        checklist = _build_checklist(evidence)
        classified = classify_all(evidence.divergences)
        metrics = _summarize_metrics(evidence)
        blockers = _blockers(
            evidence=evidence,
            checklist=checklist,
            divergences=classified,
        )
        warnings = _warnings(
            evidence=evidence,
            checklist=checklist,
            divergences=classified,
        )
        if blockers:
            state = CutoverReadinessState.BLOCKED
        elif warnings:
            state = CutoverReadinessState.WARNING
        else:
            state = CutoverReadinessState.READY
        recommendations = _recommendations(state, blockers, warnings)
        report = CutoverReadinessReport(
            validation_id=f"cutover_validation_{uuid.uuid4().hex}",
            timestamp=timestamp,
            evaluated_components=(
                "runtime_canary",
                "canary_observation",
                "policy_v2_shadow",
                "application_discovery_v2",
                "authorization_canary",
            ),
            overall_state=state,
            metrics_summary=metrics,
            blockers=tuple(dict.fromkeys(blockers)),
            warnings=tuple(dict.fromkeys(warnings)),
            recommendations=recommendations,
            divergences=classified,
            checklist=checklist.as_dict(),
        )
        self.history.record(
            metrics,
            blocked=state is CutoverReadinessState.BLOCKED,
        )
        return report


def _build_checklist(evidence: CutoverValidationInput) -> CutoverChecklist:
    return CutoverChecklist(
        contracts={name: name in evidence.available_contracts for name in _REQUIRED_CONTRACTS},
        observability={
            "shadow_active": evidence.shadow_active,
            "canary_active": evidence.canary_active,
            "metrics_available": evidence.metrics_available,
            "no_critical_errors": evidence.no_critical_errors,
        },
        security={
            "shadow_no_execution": evidence.shadow_no_execution,
            "forbidden_imports_absent": evidence.ast_boundaries_clean,
            "no_productive_grants": evidence.no_productive_grants,
            "no_policy_bypass": evidence.no_policy_bypass,
        },
    )


def _summarize_metrics(
    evidence: CutoverValidationInput,
) -> dict[str, int | float]:
    runtime = evidence.runtime_canary_metrics
    observation = evidence.observation_metrics
    policy = evidence.policy_shadow_metrics
    discovery = evidence.discovery_metrics
    authorization = evidence.authorization_metrics
    return {
        "total_events": int(observation.get("total_events", 0)),
        "matched_decisions": int(runtime.get("matched_decisions", 0)),
        "divergent_decisions": int(runtime.get("divergent_decisions", 0)),
        "policy_match_rate": float(policy.get("match_rate", 0.0)),
        "discovery_match_rate": float(discovery.get("match_rate", 0.0)),
        "authorization_match_rate": float(authorization.get("match_rate", 0.0)),
        "average_latency": float(observation.get("average_latency", 0.0)),
        "max_latency": float(observation.get("max_latency", 0.0)),
    }


def _blockers(
    *,
    evidence: CutoverValidationInput,
    checklist: CutoverChecklist,
    divergences: tuple[ClassifiedDivergence, ...],
) -> list[str]:
    values = [f"missing_contract:{name}" for name, passed in checklist.contracts.items() if not passed]
    values.extend(f"security_check_failed:{name}" for name, passed in checklist.security.items() if not passed)
    if not evidence.identity_present:
        values.append("missing_identity")
    if not evidence.policy_context_present:
        values.append("missing_policy_context")
    if not evidence.authorization_consistent:
        values.append("authorization_inconsistent")
    if evidence.replay_possible:
        values.append("replay_possible")
    if not evidence.discovery_evidence_present:
        values.append("discovery_missing_evidence")
    if evidence.health_status is CanaryHealthStatus.CRITICAL:
        values.append("canary_health_failed")
    if not evidence.no_critical_errors:
        values.append("critical_canary_errors")
    values.extend(f"critical_divergence:{item.code}" for item in divergences if item.critical)
    return values


def _warnings(
    *,
    evidence: CutoverValidationInput,
    checklist: CutoverChecklist,
    divergences: tuple[ClassifiedDivergence, ...],
) -> list[str]:
    values = [
        f"observability_incomplete:{name}"
        for name, passed in checklist.observability.items()
        if not passed and name != "no_critical_errors"
    ]
    if evidence.health_status in {
        CanaryHealthStatus.WARNING,
        CanaryHealthStatus.OBSERVING,
    }:
        values.append(f"canary_health:{evidence.health_status.value.lower()}")
    values.extend(f"known_divergence:{item.code}" for item in divergences if not item.critical)
    if int(evidence.observation_metrics.get("total_events", 0)) == 0:
        values.append("insufficient_observation_data")
    return values


def _recommendations(
    state: CutoverReadinessState,
    blockers: list[str],
    warnings: list[str],
) -> tuple[str, ...]:
    if state is CutoverReadinessState.BLOCKED:
        return (
            "No realizar cutover.",
            "Resolver todos los bloqueadores y repetir la observación canary.",
        )
    if state is CutoverReadinessState.WARNING:
        return (
            "No realizar cutover todavía.",
            "Ampliar evidencia y revisar las advertencias clasificadas.",
        )
    return (
        "La evidencia satisface los gates actuales.",
        "Requerir revisión independiente antes de cualquier cutover.",
    )
