"""Deterministic logical routing with no runtime invocation."""

import hashlib
from datetime import datetime, timezone
from enum import Enum
from sentinel.contracts import DecisionResultV1

from .activation import ActivationState, ControlledRuntimeActivation
from .audit import ActivationAudit
from .canary_policy import CanaryEligibilityPolicy, CanaryRoutingEvidenceV1
from .metrics import ActivationMetrics


class RuntimeSelection(str, Enum):
    LEGACY = "LEGACY"
    V2_CANARY = "V2_CANARY"


class RuntimeRouteDecisionV1(DecisionResultV1):
    decision_id: str
    request_id: str
    selected_runtime: RuntimeSelection
    reason_codes: tuple[str, ...]


class ControlledRuntimeRouter:
    def __init__(
        self,
        *,
        activation: ControlledRuntimeActivation,
        metrics: ActivationMetrics | None = None,
        audit: ActivationAudit | None = None,
        policy: CanaryEligibilityPolicy | None = None,
    ) -> None:
        self.activation = activation
        self.metrics = metrics or ActivationMetrics()
        self.audit = audit or ActivationAudit()
        self.policy = policy or CanaryEligibilityPolicy()
        self._decisions: dict[str, RuntimeRouteDecisionV1] = {}

    def route(
        self,
        evidence: CanaryRoutingEvidenceV1,
    ) -> RuntimeRouteDecisionV1:
        existing = self._decisions.get(evidence.request_id)
        if existing is not None:
            return existing
        selected, reasons = self._select(evidence)
        decision = RuntimeRouteDecisionV1(
            decision_id=_decision_id(evidence.request_id, selected.value),
            request_id=evidence.request_id,
            selected_runtime=selected,
            reason_codes=reasons,
        )
        self._decisions[evidence.request_id] = decision
        blocked = any(
            reason
            in {
                "READINESS_NOT_APPROVED",
                "SAFETY_NOT_HEALTHY",
                "ROLLBACK_UNAVAILABLE",
                "CRITICAL_DIVERGENCE",
            }
            for reason in reasons
        )
        self.metrics.record_route(
            v2=selected is RuntimeSelection.V2_CANARY,
            blocked=blocked,
        )
        self.audit.record(
            "v2_selected" if selected is RuntimeSelection.V2_CANARY else "legacy_selected",
            selected.value,
        )
        return decision

    def force_legacy(self, request_id: str) -> RuntimeRouteDecisionV1:
        existing = self._decisions.get(request_id)
        if existing is not None and existing.reason_codes == ("ROLLBACK_TO_LEGACY",):
            return existing
        decision = RuntimeRouteDecisionV1(
            decision_id=_decision_id(request_id, "ROLLBACK_TO_LEGACY"),
            request_id=request_id,
            selected_runtime=RuntimeSelection.LEGACY,
            reason_codes=("ROLLBACK_TO_LEGACY",),
        )
        self._decisions[request_id] = decision
        return decision

    def _select(
        self,
        evidence: CanaryRoutingEvidenceV1,
    ) -> tuple[RuntimeSelection, tuple[str, ...]]:
        if self.activation.state is not ActivationState.CANARY_ACTIVE:
            return RuntimeSelection.LEGACY, ("CANARY_NOT_ACTIVE",)
        elapsed = (datetime.now(timezone.utc) - evidence.trial_started_at).total_seconds()
        eligible, failures = self.policy.eligible(
            evidence,
            trial_expired=elapsed > evidence.maximum_trial_seconds,
        )
        if not eligible:
            return RuntimeSelection.LEGACY, failures
        bucket = (
            int(
                hashlib.sha256(evidence.request_id.encode("utf-8")).hexdigest()[:8],
                16,
            )
            % 100
        )
        threshold = 100 - self.activation.control.traffic_percentage
        if bucket < threshold:
            return RuntimeSelection.LEGACY, ("OUTSIDE_CANARY_BUCKET",)
        return RuntimeSelection.V2_CANARY, ("CANARY_BUCKET_SELECTED",)


def _decision_id(request_id: str, selection: str) -> str:
    digest = hashlib.sha256(f"{request_id}:{selection}".encode("utf-8")).hexdigest()[:32]
    return f"route_{digest}"
