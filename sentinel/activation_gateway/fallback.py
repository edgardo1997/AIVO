"""Logical fallback decision with no runtime side effects."""

import uuid
from datetime import datetime, timezone

from .audit import ActivationGatewayAudit
from .decision import AuthoritySelectionDecisionV1, SelectedAuthority
from .metrics import ActivationGatewayMetrics


class GatewayFallback:
    def __init__(
        self,
        *,
        metrics: ActivationGatewayMetrics,
        audit: ActivationGatewayAudit,
    ) -> None:
        self.metrics = metrics
        self.audit = audit

    def require_legacy(self) -> AuthoritySelectionDecisionV1:
        self.metrics.record_fallback()
        self.audit.record("fallback_required", "LEGACY_ONLY")
        return AuthoritySelectionDecisionV1(
            decision_id=f"fallback_{uuid.uuid4().hex}",
            selected_authority=SelectedAuthority.LEGACY_ONLY,
            reason_codes=("V2_CANDIDATE_FAILURE",),
            validation_summary=("LOGICAL_FALLBACK_ONLY",),
            timestamp=datetime.now(timezone.utc),
        )
