import logging
import time
from typing import Any, Dict, List, Optional

from sentinel.core.consent_manager import (
    ConsentGrant,
    ConsentManager,
    ConsentType,
    PendingConsent,
)
from sentinel.core.intent import Intent
from sentinel.core.planner import Plan
from sentinel.core.risk_classifier import RiskClassifier, RiskClassification

log = logging.getLogger("sentinel.consent")


class ConsentService:
    def __init__(self, knowledge_service=None):
        self._manager = ConsentManager()
        self._classifier = RiskClassifier(knowledge_service=knowledge_service)
        self._audit = None

    def set_audit_service(self, audit_svc) -> None:
        self._audit = audit_svc

    @property
    def manager(self) -> ConsentManager:
        return self._manager

    @property
    def classifier(self) -> RiskClassifier:
        return self._classifier

    def set_risk_classifier(self, classifier: RiskClassifier) -> None:
        self._classifier = classifier

    def classify_plan(
        self,
        intent: Intent,
        plan: Plan,
        context: Optional[Dict[str, Any]] = None,
        simulation_result=None,
    ) -> RiskClassification:
        return self._classifier.classify(intent, plan, context, simulation_result)

    def check_existing_consent(
        self,
        user_id: str,
        tool_id: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Optional[ConsentGrant]:
        return self._manager.check_consent(user_id, tool_id, params)

    def record_request(
        self,
        user_id: str,
        tool_id: str,
        action_id: str,
        risk_level: str = "unknown",
    ) -> None:
        """Registra una solicitud de consentimiento sin crear PendingConsent.
        Único punto de emisión para evento consent_requested."""
        if self._audit:
            self._audit.log_action(
                action="consent_requested",
                details=f"Consent requested for {tool_id} by {user_id} action={action_id} risk={risk_level}",
                status="pending",
                user=user_id,
            )

    def record_decision(
        self,
        action_id: str,
        user_id: str,
        tool_id: str,
        approved: bool,
        reason: str = "",
    ) -> None:
        """Registra la decisión del usuario sobre una solicitud de consentimiento.
        Único punto de emisión para eventos consent_granted/consent_denied."""
        action = "consent_granted" if approved else "consent_denied"
        status = "granted" if approved else "denied"
        if self._audit:
            self._audit.log_action(
                action=action,
                details=f"Consent {'granted' if approved else 'denied'} by {user_id} for {tool_id} action={action_id}",
                status=status,
                user=user_id,
            )

    def request_consent(
        self,
        user_id: str,
        tool_id: str,
        params: Dict[str, Any],
        risk: RiskClassification,
        plan_data: Dict[str, Any],
        intent_data: Dict[str, Any],
        context_summary: Dict[str, Any],
    ) -> PendingConsent:
        pending = self._manager.request_consent(
            user_id=user_id,
            tool_id=tool_id,
            params=params,
            risk_level=risk.level.value,
            risk_label=risk.label,
            risk_description=risk.description,
            is_read_only=risk.is_read_only,
            is_reversible=risk.is_reversible,
            affected_resources=risk.affected_resources,
            estimated_impact=risk.estimated_impact,
            simulation_summary=risk.simulation_summary,
            plan_data=plan_data,
            intent_data=intent_data,
            context_summary=context_summary,
        )
        self.record_request(user_id, tool_id, pending.id, risk.level.value)
        return pending

    def respond_consent(
        self,
        pending_id: str,
        user_id: str,
        approved: bool,
        consent_type: Optional[str] = None,
        session_id: Optional[str] = None,
        *,
        tool_id: Optional[str] = None,
        risk_level: Optional[str] = None,
        risk_label: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not approved:
            pending = self._manager.get_pending(pending_id)
            if pending and pending.user_id == user_id:
                self._manager._pending.pop(pending_id, None)
                self.record_decision(pending_id, user_id, pending.tool_id, approved=False)
            return {"approved": False, "status": "cancelled"}

        ctype = ConsentType(consent_type or "once")
        grant = self._manager.grant_consent(pending_id, user_id, ctype, session_id=session_id)
        if not grant:
            return {"approved": False, "status": "expired_or_invalid"}
        self.record_decision(grant.id, user_id, grant.tool_id, approved=True)
        return {
            "approved": True,
            "consent_type": ctype.value,
            "grant_id": grant.id,
        }

    def revoke_consent(self, grant_id: str, user_id: str) -> bool:
        ok = self._manager.revoke_consent(grant_id, user_id)
        if ok and self._audit:
            self._audit.log_action(
                action="consent_revoked",
                details=f"Consent {grant_id} revoked by {user_id}",
                status="revoked",
                user=user_id,
            )
        return ok

    def revoke_all(self, user_id: str) -> int:
        count = self._manager.revoke_all(user_id)
        if count and self._audit:
            self._audit.log_action(
                action="consent_revoked",
                details=f"All consents revoked by {user_id} ({count} grants)",
                status="revoked",
                user=user_id,
            )
        return count

    def list_grants(self, user_id: str) -> List[ConsentGrant]:
        return self._manager.list_grants(user_id)

    def list_pending(self, user_id: str) -> List[PendingConsent]:
        return self._manager.list_pending(user_id)
