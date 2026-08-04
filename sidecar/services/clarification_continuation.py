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
    new_correlation_id: str = ""
    parent_request_id: str = ""
    state: str = "created"  # see ContinuationState enum below
    version: int = 1
    idempotency_key: str = ""
    result_summary: str = ""
    execution_id: str = ""
    verification_id: str = ""
    started_at: str = ""
    completed_at: str = ""
    audit_events: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["material_change_flags"] = asdict(self.material_change_flags)
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ClarifiedRequestContext":
        flags = data.get("material_change_flags", {})
        if not isinstance(flags, dict):
            flags = {}
        ctx = cls(
            original_request_id=data.get("original_request_id", data.get("original_request_id", "")),
            original_correlation_id=data.get("original_correlation_id", ""),
            clarification_id=data.get("clarification_id", ""),
            clarification_version=data.get("clarification_version", 1),
            original_input_understanding_id=data.get("original_input_understanding_id", ""),
            original_ambiguity_decision_id=data.get("original_ambiguity_decision_id", ""),
            selected_candidate_id=data.get("selected_candidate_id", ""),
            free_text_response=data.get("free_text_response", ""),
            resolved_utterance=data.get("resolved_utterance", ""),
            resolved_target=data.get("resolved_target", ""),
            resolution_source=data.get("resolution_source", ""),
            user_id=data.get("user_id", ""),
            session_id=data.get("session_id", ""),
            created_at=data.get("created_at", ""),
            material_change_flags=MaterialChangeFlags(**flags),
            prior_plan_digest=data.get("prior_plan_digest", ""),
            prior_action_digest=data.get("prior_action_digest", ""),
            prior_argument_digest=data.get("prior_argument_digest", ""),
            continuation_id=data.get("continuation_id", ""),
            new_correlation_id=data.get("new_correlation_id", ""),
            parent_request_id=data.get("parent_request_id", ""),
            state=data.get("state", "created"),
            version=data.get("version", 1),
            idempotency_key=data.get("idempotency_key", ""),
            result_summary=data.get("result_summary", ""),
            execution_id=data.get("execution_id", ""),
            verification_id=data.get("verification_id", ""),
            started_at=data.get("started_at", ""),
            completed_at=data.get("completed_at", ""),
            audit_events=list(data.get("audit_events", [])),
        )
        return ctx

    def transition(self, new_state: str) -> bool:
        """Validate and perform an allowed state transition."""
        allowed = {
            "created": {"replanning", "cancelled", "expired"},
            "replanning": {"awaiting_confirmation", "clarification_required_again", "denied", "failed", "cancelled"},
            "clarification_required_again": {"replanning", "cancelled", "expired"},
            "awaiting_confirmation": {"authorized", "denied", "cancelled", "expired"},
            "authorized": {"executing", "cancelled"},
            "executing": {"verified_completed", "failed", "interrupted", "cancelled"},
            "verified_completed": set(),
            "failed": set(),
            "interrupted": set(),
            "cancelled": set(),
            "expired": set(),
            "superseded": set(),
            "denied": set(),
        }
        if new_state not in allowed.get(self.state, set()):
            return False
        self.state = new_state
        self.version += 1
        return True


class ContinuationState:
    CREATED = "created"
    SUPERSEDED = "superseded"
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
        import re

        new_correlation_id = str(uuid.uuid4())
        parent_request_id = record.original_request_id or record.correlation_id
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
            new_correlation_id=new_correlation_id,
            parent_request_id=parent_request_id,
            state=ContinuationState.CREATED,
            idempotency_key=idempotency_key,
        )
        continuation.audit_events.append({
            "event": "continuation_created",
            "correlation_id": continuation.original_correlation_id,
            "clarification_id": continuation.clarification_id,
            "continuation_id": continuation.continuation_id,
            "new_correlation_id": new_correlation_id,
        })
        try:
            from repositories.execution_grant_repository import ExecutionGrantRepository
            grant_repo = ExecutionGrantRepository()
            grant_repo.invalidate_by_plan_id(
                plan_id=parent_request_id,
                session_id=record.session_id,
                reason="prior_grant_invalidated_by_clarification",
                invalidation_context={
                    "clarification_id": record.clarification_id,
                    "continuation_id": continuation.continuation_id,
                    "resolved_utterance": re.sub(r"\s+", " ", resolved_utterance)[:200],
                },
                actor={
                    "user_id": record.user_id,
                    "session_id": record.session_id,
                },
            )
        except Exception:
            pass
        self._store.put(continuation)
        self._audit.log_action(
            "clarification_continuation_created",
            str(continuation.continuation_id),
            user=record.user_id,
        )
        return continuation

    def get(self, continuation_id: str) -> Optional[ClarifiedRequestContext]:
        raw = self._store.get(continuation_id)
        if raw is None:
            return None
        try:
            return ClarifiedRequestContext.from_dict(raw)
        except Exception:
            return None
