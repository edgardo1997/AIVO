"""Authoritative continuation consumer.

Loads a ClarifiedRequestContext and runs it through the same governed
Orchestrator used for ordinary actions, then stores the result and emits a
fresh confirmation request. It does not execute tools until a fresh grant is
issued.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from services.clarification_continuation import (
    ClarifiedRequestContext,
    ContinuationService,
    ContinuationState,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class ContinuationExecutor:
    """Single authoritative consumer for a clarified continuation."""

    def __init__(self, continuation_service: Optional[ContinuationService] = None):
        self._svc = continuation_service or ContinuationService()

    async def start(
        self,
        continuation_id: str,
        user_id: str,
        session_id: str,
        identity: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Run the continuation through the governed pipeline (dry run)."""
        ctx = self._svc.get(continuation_id)
        if ctx is None:
            return None
        if ctx.user_id != user_id or ctx.session_id != session_id:
            return None
        if ctx.state not in {ContinuationState.CREATED, ContinuationState.CLARIFICATION_RESOLVED}:
            return self._as_response(ctx)

        if not ctx.transition(ContinuationState.REPLANNING):
            return self._as_response(ctx)

        ctx.started_at = _now()
        ctx.audit_events.append({
            "event": "continuation_started",
            "continuation_id": ctx.continuation_id,
            "correlation_id": ctx.original_correlation_id,
            "new_correlation_id": ctx.new_correlation_id,
            "started_at": ctx.started_at,
        })

        try:
            from modules.sentinel_bridge_helpers import get_orchestrator
            orchestrator = get_orchestrator()
            result = await orchestrator.process(
                ctx.resolved_utterance,
                identity=identity or {},
                session_id=session_id,
                dry_run=True,
                timeout=60.0,
            )

            if result and getattr(result, "error", None):
                ctx.transition(ContinuationState.FAILED)
                ctx.result_summary = f"replanning_failed: {result.error}"
            else:
                ctx.transition(ContinuationState.AWAITING_CONFIRMATION)
                plan = getattr(result, "plan", None)
                plan_text = ""
                if plan:
                    plan_text = getattr(plan, "summary", "") or ""
                ctx.result_summary = plan_text or "replanning_complete_requires_confirmation"
                ctx.audit_events.append({
                    "event": "replanning_complete",
                    "continuation_id": ctx.continuation_id,
                    "new_correlation_id": ctx.new_correlation_id,
                    "requires_confirmation": True,
                })
        except Exception as exc:
            ctx.transition(ContinuationState.FAILED)
            ctx.result_summary = f"replanning_exception: {exc}"

        ctx.completed_at = _now()
        self._svc._store.put(ctx)
        return self._as_response(ctx)

    def get(self, continuation_id: str, user_id: str, session_id: str) -> Optional[Dict[str, Any]]:
        ctx = self._svc.get(continuation_id)
        if ctx is None or ctx.user_id != user_id or ctx.session_id != session_id:
            return None
        return self._as_response(ctx)

    def _as_response(self, ctx: ClarifiedRequestContext) -> Dict[str, Any]:
        return {
            "continuation_id": ctx.continuation_id,
            "clarification_id": ctx.clarification_id,
            "state": ctx.state,
            "version": ctx.version,
            "resolved_utterance": ctx.resolved_utterance,
            "resolved_target": ctx.resolved_target,
            "requires_confirmation": ctx.state == ContinuationState.AWAITING_CONFIRMATION,
            "result_summary": ctx.result_summary,
            "audit_events": ctx.audit_events,
        }
