"""Authoritative continuation consumer.

Loads a ClarifiedRequestContext and runs it through the same governed
Orchestrator used for ordinary actions, then stores the result and emits a
fresh confirmation request. It does not execute tools until a fresh grant is
issued.
"""

from __future__ import annotations

import dataclasses
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from services.clarification_continuation import (
    ClarifiedRequestContext,
    ContinuationService,
    ContinuationState,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _now_plus(minutes: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat().replace("+00:00", "Z")


def _safe_plan_dict(plan: Any) -> Optional[Dict[str, Any]]:
    """Serialize a Plan into a JSON-safe canonical dict for hashing."""
    if plan is None:
        return None
    steps = []
    for step in getattr(plan, "steps", []) or []:
        steps.append({
            "id": getattr(step, "id", ""),
            "tool_id": getattr(step, "tool_id", ""),
            "params": getattr(step, "params", {}),
            "description": getattr(step, "description", ""),
            "is_reversible": bool(getattr(step, "is_reversible", False)),
        })
    return {
        "steps": steps,
        "description": getattr(plan, "description", ""),
        "risk_score": float(getattr(plan, "risk_score", 0.0) or 0.0),
    }


def _risk_label(score: float) -> str:
    if score < 0.3:
        return "low"
    if score < 0.7:
        return "medium"
    return "high"


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
        """Run the continuation through the governed pipeline (dry run) and create a fresh plan grant."""
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
                plan = getattr(result, "plan", None)
                plan_dict = _safe_plan_dict(plan)
                broker = self._get_broker(orchestrator)
                if plan_dict is not None and broker is not None:
                    plan_payload, plan_hash = broker.canonical_plan(plan_dict)
                    identity_hash = broker._hash({"user_id": user_id, "session_id": session_id})
                    plan_grant_id = broker.request_plan_grant(
                        user_id=user_id,
                        session_id=session_id,
                        identity_hash=identity_hash,
                        plan_id=ctx.continuation_id,
                        plan_hash=plan_hash,
                        plan_payload=plan_payload,
                        risk_level=_risk_label(plan_dict.get("risk_score", 0.0)),
                        expires_at=_now_plus(10),
                        simulation_evidence={"summary": plan_dict.get("description", "")},
                    )
                    ctx.confirmation_id = plan_grant_id
                    ctx.plan_digest = plan_hash
                    ctx.prior_action_digest = _hash_of(plan_dict.get("steps", []))
                else:
                    ctx.confirmation_id = ""
                ctx.transition(ContinuationState.AWAITING_CONFIRMATION)
                plan_text = getattr(plan, "summary", "") or getattr(plan, "description", "") or "replanning_complete_requires_confirmation"
                ctx.result_summary = plan_text
                ctx.audit_events.append({
                    "event": "replanning_complete",
                    "continuation_id": ctx.continuation_id,
                    "new_correlation_id": ctx.new_correlation_id,
                    "requires_confirmation": True,
                    "confirmation_id": ctx.confirmation_id,
                })
        except Exception as exc:
            ctx.transition(ContinuationState.FAILED)
            ctx.result_summary = f"replanning_exception: {exc}"

        ctx.completed_at = _now()
        self._svc._store.put(ctx)
        return self._as_response(ctx)

    async def confirm(
        self,
        continuation_id: str,
        user_id: str,
        session_id: str,
        approved: bool,
        identity: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Validate plan grant, re-check for TOCTOU, and execute if approved."""
        ctx = self._svc.get(continuation_id)
        if ctx is None or ctx.user_id != user_id or ctx.session_id != session_id:
            return None
        if ctx.state != ContinuationState.AWAITING_CONFIRMATION:
            return self._as_response(ctx)

        if not approved:
            ctx.transition(ContinuationState.DENIED)
            ctx.audit_events.append({
                "event": "confirmation_denied",
                "continuation_id": ctx.continuation_id,
                "confirmation_id": ctx.confirmation_id,
            })
            self._svc._store.put(ctx)
            return self._as_response(ctx)

        from modules.sentinel_bridge_helpers import get_orchestrator
        orchestrator = get_orchestrator()
        broker = self._get_broker(orchestrator)

        try:
            # Re-run plan to detect TOCTOU changes.
            check = await orchestrator.process(
                ctx.resolved_utterance,
                identity=identity or {},
                session_id=session_id,
                dry_run=True,
                timeout=60.0,
            )
            plan_dict = _safe_plan_dict(getattr(check, "plan", None))
            if plan_dict is not None and broker is not None:
                _, current_hash = broker.canonical_plan(plan_dict)
                if current_hash != ctx.plan_digest:
                    ctx.transition(ContinuationState.REPLANNING)
                    ctx.result_summary = "plan_changed_replanning_required"
                    ctx.audit_events.append({
                        "event": "material_change_detected",
                        "continuation_id": ctx.continuation_id,
                        "reason": "plan_hash_mismatch",
                    })
                    self._svc._store.put(ctx)
                    return self._as_response(ctx)

            # Approve durable plan grant.
            if broker is not None and not broker.approve_plan_grant(ctx.confirmation_id, user_id=user_id):
                ctx.transition(ContinuationState.DENIED)
                ctx.result_summary = "grant_approval_failed"
                self._svc._store.put(ctx)
                return self._as_response(ctx)

            ctx.transition(ContinuationState.AUTHORIZED)
            ctx.audit_events.append({
                "event": "confirmation_accepted",
                "continuation_id": ctx.continuation_id,
                "confirmation_id": ctx.confirmation_id,
            })

            # Execute through the authoritative pipeline.
            ctx.transition(ContinuationState.EXECUTING)
            result = await orchestrator.process(
                ctx.resolved_utterance,
                identity=identity or {},
                session_id=session_id,
                dry_run=False,
                approved_plan_grant_id=ctx.confirmation_id,
                timeout=120.0,
            )

            if result and not getattr(result, "error", None) and getattr(result, "approved", False):
                ctx.transition(ContinuationState.VERIFIED_COMPLETED)
                presentation = getattr(result, "presentation", None) or {}
                ctx.result_summary = presentation.get("summary", "") or "execution_verified"
                ctx.execution_id = getattr(result, "execution_id", "") or ""
                ctx.audit_events.append({
                    "event": "execution_verified",
                    "continuation_id": ctx.continuation_id,
                    "execution_id": ctx.execution_id,
                })
            else:
                ctx.transition(ContinuationState.FAILED)
                ctx.result_summary = getattr(result, "error", "") or "execution_failed"
                ctx.audit_events.append({
                    "event": "continuation_failed",
                    "continuation_id": ctx.continuation_id,
                    "reason": ctx.result_summary,
                })
        except Exception as exc:
            ctx.transition(ContinuationState.FAILED)
            ctx.result_summary = f"execution_exception: {exc}"
            ctx.audit_events.append({
                "event": "continuation_failed",
                "continuation_id": ctx.continuation_id,
                "reason": str(exc),
            })

        ctx.completed_at = _now()
        self._svc._store.put(ctx)
        return self._as_response(ctx)

    async def cancel(
        self,
        continuation_id: str,
        user_id: str,
        session_id: str,
    ) -> Optional[Dict[str, Any]]:
        ctx = self._svc.get(continuation_id)
        if ctx is None or ctx.user_id != user_id or ctx.session_id != session_id:
            return None
        if ctx.state in {ContinuationState.VERIFIED_COMPLETED, ContinuationState.DENIED, ContinuationState.FAILED, ContinuationState.CANCELLED}:
            return self._as_response(ctx)

        from modules.sentinel_bridge_helpers import get_orchestrator
        orchestrator = get_orchestrator()
        broker = self._get_broker(orchestrator)
        if broker is not None and ctx.confirmation_id:
            try:
                broker._grants.transition_plan(
                    ctx.confirmation_id,
                    expected="pending",
                    target="cancelled",
                    actor={"user_id": user_id, "session_id": session_id},
                )
            except Exception:
                pass

        ctx.transition(ContinuationState.CANCELLED)
        ctx.audit_events.append({
            "event": "continuation_cancelled",
            "continuation_id": ctx.continuation_id,
            "confirmation_id": ctx.confirmation_id,
        })
        self._svc._store.put(ctx)
        return self._as_response(ctx)

    def get(self, continuation_id: str, user_id: str, session_id: str) -> Optional[Dict[str, Any]]:
        ctx = self._svc.get(continuation_id)
        if ctx is None or ctx.user_id != user_id or ctx.session_id != session_id:
            return None
        return self._as_response(ctx)

    @staticmethod
    def _get_broker(orchestrator: Any) -> Any:
        gateway = getattr(orchestrator, "_tool_gateway", None)
        return getattr(gateway, "_confirmation_broker", None)

    def _as_response(self, ctx: ClarifiedRequestContext) -> Dict[str, Any]:
        return {
            "continuation_id": ctx.continuation_id,
            "clarification_id": ctx.clarification_id,
            "state": ctx.state,
            "version": ctx.version,
            "resolved_utterance": ctx.resolved_utterance,
            "resolved_target": ctx.resolved_target,
            "requires_confirmation": ctx.state == ContinuationState.AWAITING_CONFIRMATION,
            "confirmation_id": ctx.confirmation_id,
            "result_summary": ctx.result_summary,
            "execution_id": ctx.execution_id,
            "audit_events": ctx.audit_events,
        }


def _hash_of(obj: Any) -> str:
    import hashlib
    payload = json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
