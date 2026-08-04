"""Clarification lifecycle service.

Authoritative owner for clarification creation, resolution, cancellation and
supersession. It does not execute tools, authorize or persist beyond the
clarification record.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from repositories.clarification_store import ClarificationRecord, ClarificationStore
from services import input_understanding_service as iu
from services.clarification_continuation import ContinuationService, MaterialChangeFlags


DEFAULT_TTL_SECONDS = 3600


class ClarificationService:
    """Create, resolve and cancel clarifications safely."""

    def __init__(
        self,
        store: Optional[ClarificationStore] = None,
        continuation_service: Optional[ContinuationService] = None,
    ):
        self._store = store or ClarificationStore()
        self._continuation = continuation_service or ContinuationService()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _expires(self) -> str:
        return (datetime.now(timezone.utc) + timedelta(seconds=DEFAULT_TTL_SECONDS)).isoformat()

    def create(
        self,
        understanding: iu.InputUnderstandingResult,
        decision: iu.AmbiguityDecision,
        session_id: str,
        user_id: str,
        original_request_id: str,
        response_language: str = "en",
        correlation_id: str = "",
    ) -> ClarificationRecord:
        """Create a durable clarification record and supersede prior pending ones."""
        candidates: List[Dict[str, Any]] = []
        candidate_ids: List[str] = []
        base = understanding.decision_id or correlation_id or str(uuid.uuid4())
        for i, target in enumerate(understanding.candidate_targets or []):
            cid = f"{base}-c{i}"
            candidate_ids.append(cid)
            candidates.append({
                "id": cid,
                "label": target,
                "description": "",
                "index": i,
            })

        question = iu.clarification_prompt(understanding, decision, response_language)

        record = ClarificationRecord(
            clarification_id=str(uuid.uuid4()),
            correlation_id=correlation_id or str(uuid.uuid4()),
            session_id=session_id,
            user_id=user_id,
            original_request_id=original_request_id,
            ambiguity_decision_id=decision.id,
            input_understanding_id=understanding.decision_id,
            question=question,
            response_language=response_language,
            ambiguity_type=understanding.ambiguity_type,
            candidate_ids=candidate_ids,
            candidate_metadata=candidates,
            free_text_allowed=decision.ask_clarification,
            allow_none=True,
            risk_if_wrong=understanding.risk_if_wrong or "",
            created_at=self._now(),
            expires_at=self._expires(),
            state="pending",
        )

        # Supersede other pending clarifications for the same user/session.
        self._store.supersede_pending(session_id, user_id, original_request_id)
        self._store.put(record)
        return record

    def get(self, clarification_id: str) -> Optional[ClarificationRecord]:
        return self._store.get(clarification_id)

    def get_pending_for_session(
        self, session_id: str, user_id: str
    ) -> Optional[ClarificationRecord]:
        records = self._store.get_pending(session_id, user_id)
        if not records:
            return None
        # Most recent pending.
        records.sort(key=lambda r: r.created_at, reverse=True)
        return records[0]

    def resolve(
        self,
        clarification_id: str,
        session_id: str,
        user_id: str,
        correlation_id: str,
        version: int,
        selected_candidate_id: str = "",
        free_text_response: str = "",
    ) -> Optional[ClarificationRecord]:
        """Resolve a clarification with strict binding and replay protection."""
        record = self._store.get(clarification_id)
        if record is None:
            return None

        if record.state != "pending":
            return None
        if record.session_id != session_id or record.user_id != user_id:
            return None
        if record.correlation_id != correlation_id:
            return None
        if record.version != version:
            return None
        if record.expires_at < self._now():
            record.state = "expired"
            self._store.put(record)
            return None

        # Validate the answer belongs to this clarification.
        if selected_candidate_id:
            if selected_candidate_id == "none":
                # Treat "none" as a user cancellation.
                return self.cancel(clarification_id, session_id, user_id, correlation_id, version)
            if selected_candidate_id not in record.candidate_ids:
                return None
        else:
            if not (record.free_text_allowed and free_text_response.strip()):
                return None

        record.selected_candidate_id = selected_candidate_id
        record.free_text_response = free_text_response.strip()
        record.answered_at = self._now()
        record.state = "answered"
        record.version = record.version + 1

        # Build resolved target/action without re-running full engines.
        if selected_candidate_id:
            index = record.candidate_ids.index(selected_candidate_id)
            target = record.candidate_metadata[index].get("label", "")
            record.resolved_target = target
            record.resolved_utterance = f"{record.ambiguity_type}: {target}"
        elif free_text_response:
            record.resolved_utterance = free_text_response

        record.resolved_action = "proceed"
        record.state = "consumed"

        # Treat the clarified answer as a new interpretation.
        flags = MaterialChangeFlags(
            intent_changed=True,
            target_changed=bool(record.resolved_target),
            arguments_changed=bool(record.free_text_response),
        )
        continuation = self._continuation.create_continuation(
            record=record,
            resolved_utterance=record.resolved_utterance,
            resolved_target=record.resolved_target,
            material_change_flags=flags,
            idempotency_key=f"{record.clarification_id}:{record.version}",
        )
        record.continuation_id = continuation.continuation_id
        self._store.put(record)
        return record

    def cancel(
        self,
        clarification_id: str,
        session_id: str,
        user_id: str,
        correlation_id: str,
        version: int,
    ) -> Optional[ClarificationRecord]:
        record = self._store.get(clarification_id)
        if record is None:
            return None
        if record.state != "pending":
            return None
        if record.session_id != session_id or record.user_id != user_id:
            return None
        if record.correlation_id != correlation_id:
            return None
        if record.version != version:
            return None
        record.answered_at = self._now()
        record.state = "cancelled"
        record.version = record.version + 1
        self._store.put(record)
        return record

    def to_stream_event(self, record: ClarificationRecord) -> Dict[str, Any]:
        """Safe event shape for the NDJSON stream."""
        return {
            "type": "clarification",
            "clarification_id": record.clarification_id,
            "correlation_id": record.correlation_id,
            "question": record.question,
            "response_language": record.response_language,
            "ambiguity_type": record.ambiguity_type,
            "options": [
                {"id": c["id"], "label": c["label"], "description": c.get("description", "")}
                for c in record.candidate_metadata
            ],
            "allow_free_text": record.free_text_allowed,
            "allow_none": record.allow_none,
            "risk_if_wrong": record.risk_if_wrong,
            "expires_at": record.expires_at,
            "version": record.version,
        }
