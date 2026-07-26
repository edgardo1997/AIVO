"""Non-executing gateway that only evaluates future eligibility."""

import uuid
from datetime import datetime, timezone

from .audit import ActivationGatewayAudit
from .control import ActivationGatewayControl
from .decision import AuthoritySelectionDecisionV1, SelectedAuthority
from .metrics import ActivationGatewayMetrics
from .policy import ActivationSelectionPolicy, GatewayEvidenceV1


class ActivationGateway:
    def __init__(
        self,
        *,
        control: ActivationGatewayControl,
        metrics: ActivationGatewayMetrics | None = None,
        audit: ActivationGatewayAudit | None = None,
        policy: ActivationSelectionPolicy | None = None,
    ) -> None:
        self.control = control
        self.metrics = metrics or ActivationGatewayMetrics()
        self.audit = audit or ActivationGatewayAudit()
        self.policy = policy or ActivationSelectionPolicy()

    def evaluate(
        self,
        evidence: GatewayEvidenceV1,
    ) -> AuthoritySelectionDecisionV1 | None:
        if not self.control.enabled:
            return None
        try:
            selected, reasons, summary = self.policy.evaluate(
                evidence,
                v2_allowed=self.control.v2_allowed,
            )
        except Exception:
            self.metrics.record_error()
            selected = SelectedAuthority.BLOCKED
            reasons = ("POLICY_EVALUATION_ERROR",)
            summary = ("VALIDATION_FAILED",)
        self.metrics.record_selection(selected)
        self.audit.record("gateway_evaluated", selected.value)
        event = {
            SelectedAuthority.LEGACY_ONLY: "legacy_selected",
            SelectedAuthority.V2_NOT_AVAILABLE: "legacy_selected",
            SelectedAuthority.V2_ELIGIBLE_SHADOW: "v2_candidate_selected",
            SelectedAuthority.V2_ELIGIBLE_CANARY: "v2_candidate_selected",
            SelectedAuthority.BLOCKED: "selection_blocked",
        }[selected]
        self.audit.record(event, selected.value)
        return AuthoritySelectionDecisionV1(
            decision_id=f"gateway_{uuid.uuid4().hex}",
            selected_authority=selected,
            reason_codes=reasons,
            validation_summary=summary,
            timestamp=datetime.now(timezone.utc),
        )
