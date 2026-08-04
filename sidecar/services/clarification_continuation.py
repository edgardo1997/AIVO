"""Clarified-request continuation contract.

This is a lightweight, deterministic server-side record that links a
clarification answer to a fresh reasoning pass.  It does not execute tools
and it does not store secrets, prompts or hidden reasoning.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from repositories.continuation_store import ContinuationStore
from services.audit_service import AuditService


@dataclass
class MaterialChangeFlags:
    intent_changed: bool = False
    tool_changed: bool = False
    target_changed: bool = False
    scope_changed: bool = False
    arguments_changed: bool = False
    provider_changed: bool = False
    data_classification_changed: bool = False
    cost_changed: bool = False
    risk_changed: bool = False
    destructiveness_changed: bool = False

    def any(self) -> bool:
        return any(asdict(self).values())


@dataclass
class ClarifiedRequestContext:
    original_request_id: str
    original_correlation_id: str
    clarification_id: str
    clarification_version: int
    original_input_understanding_id: str
    original_ambiguity_decision_id: str
    selected_candidate_id: str
    free_text_response: str
    resolved_utterance: str
    resolved_target: str
    resolution_source: str
    user_id: str
    session_id: str
    created_at: str
    material_change_flags: MaterialChangeFlags = field(default_factory=MaterialChangeFlags)
    prior_plan_digest: str = ""
    prior_action_digest: str = ""
    prior_argument_digest: str = ""
    continuation_id: str = ""
    state: str = "clarification_resolved"  # see ContinuationState enum below
    idempotency_key: str = ""
    audit_events: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["material_change_flags"] = asdict(self.material_change_flags)
        return data


class ContinuationState:
    CLARIFICATION_PENDING = "clarification_pending"
    CLARIFICATION_RESOLVED = "clarification_resolved"
    REPLANNING = "replanning"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    AUTHORIZED = "authorized"
    EXECUTING = "executing"
    VERIFIED_COMPLETED = "verified_completed"
    CANCELLED = "cancelled"
    DENIED = "denied"
    FAILED = "failed"
    INTERRUPTED = "interrupted"
    EXPIRED = "expired"


class ContinuationService:
    """Server-side owner of the clarified-request continuation contract."""

    def __init__(self, store: Optional[ContinuationStore] = None):
        self._store = store or ContinuationStore()
        self._audit = AuditService()

    def create_continuation(
        self,
        record: Any,
        resolved_utterance: str,
        resolved_target: str,
        material_change_flags: MaterialChangeFlags,
        idempotency_key: str,
    ) -> ClarifiedRequestContext:
        """Create a durable continuation context after a valid clarification."""
        continuation = ClarifiedRequestContext(
            original_request_id=record.original_request_id,
            original_correlation_id=record.correlation_id,
            clarification_id=record.clarification_id,
            clarification_version=record.version,
            original_input_understanding_id=record.input_understanding_id,
            original_ambiguity_decision_id=record.ambiguity_decision_id,
            selected_candidate_id=record.selected_candidate_id,
            free_text_response=record.free_text_response,
            resolved_utterance=resolved_utterance,
            resolved_target=resolved_target,
            resolution_source="candidate" if record.selected_candidate_id else "free_text",
            user_id=record.user_id,
            session_id=record.session_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            material_change_flags=material_change_flags,
            prior_action_digest=record.resolved_action,
            prior_argument_digest=record.resolved_target,
            continuation_id=str(uuid.uuid4()),
            state=ContinuationState.REPLANNING,
            idempotency_key=idempotency_key,
        )
        continuation.audit_events.append({
            "event": "continuation_created",
            "correlation_id": continuation.original_correlation_id,
            "clarification_id": continuation.clarification_id,
            "continuation_id": continuation.continuation_id,
        })
        self._store.put(continuation)
        self._audit.log_action(
            "clarification_continuation_created",
            str(continuation.continuation_id),
            user=record.user_id,
        )
        return continuation

    def get(self, continuation_id: str) -> Optional[ClarifiedRequestContext]:
        return self._store.get(continuation_id)
