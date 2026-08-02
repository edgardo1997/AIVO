"""Production wiring for the durable PlanApprovalGrant flow.

This is the single production seam that exercises the full durable chain:

    Orchestrator (resume_approved_plan)
      -> ConfirmationBroker (request_plan_grant / approve_plan_grant)
      -> ExecutionGrantRepository -> plan_approval_grants / step_execution_grants
      -> ExecutionPipeline -> ToolExecutionGuard -> ToolGateway -> Executor

It is deliberately minimal: it does NOT bypass any authority.  The plan is
first persisted and approved as a durable PlanApprovalGrant, then executed by
resuming that grant through Orchestrator.resume_approved_plan(), which issues
per-step StepExecutionGrants that the ToolExecutionGuard enforces.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from sentinel.core.confirmation import ConfirmationBroker

log = logging.getLogger("sentinel.v1.plans")
router = APIRouter()

_DEFAULT_TTL_MINUTES = 15


class PlanApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: str
    plan: Dict[str, Any]
    risk_level: str = "unknown"
    expires_at: Optional[str] = None


class ResumeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_grant_id: str


def _broker() -> ConfirmationBroker:
    from modules import get_gateway

    gateway = get_gateway()
    broker = getattr(gateway, "_confirmation_broker", None)
    if broker is None:
        raise HTTPException(status_code=503, detail="Durable confirmation broker is unavailable")
    return broker


@router.post("/plans/approve", status_code=200)
async def approve_plan(req: PlanApprovalRequest, request: Request):
    from modules.auth import request_identity

    identity = request_identity(request).to_dict()
    user_id = identity.get("user_id")
    session_id = identity.get("session_id") or ""
    if not user_id:
        raise HTTPException(status_code=401, detail="Authenticated user is required")
    if not isinstance(req.plan, dict) or not req.plan.get("steps"):
        raise HTTPException(status_code=422, detail="plan.steps is required")

    broker = _broker()
    try:
        payload, plan_hash = ConfirmationBroker.canonical_plan(req.plan)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    identity_hash = ConfirmationBroker._hash({"user_id": user_id, "session_id": session_id})
    expires_at = req.expires_at or (
        (datetime.now(timezone.utc) + timedelta(minutes=_DEFAULT_TTL_MINUTES)).isoformat().replace("+00:00", "Z")
    )

    grant_id = broker.request_plan_grant(
        user_id=user_id,
        session_id=session_id,
        identity_hash=identity_hash,
        plan_id=req.plan_id,
        plan_hash=plan_hash,
        plan_payload=payload,
        risk_level=req.risk_level,
        expires_at=expires_at,
        simulation_evidence={},
    )
    if not broker.approve_plan_grant(grant_id, user_id=user_id):
        raise HTTPException(status_code=409, detail="Plan grant could not be approved")

    log.info("Durable PlanApprovalGrant created and approved: grant=%s plan=%s", grant_id, req.plan_id)
    return {
        "plan_grant_id": grant_id,
        "plan_id": req.plan_id,
        "plan_hash": plan_hash,
        "expires_at": expires_at,
    }


@router.post("/plans/resume", status_code=200)
async def resume_plan(req: ResumeRequest, request: Request):
    from modules.auth import request_identity
    from modules.sentinel_bridge_helpers import get_orchestrator

    identity = request_identity(request).to_dict()
    orchestrator = get_orchestrator()
    result = await orchestrator.resume_approved_plan(req.plan_grant_id, identity)
    if result.error:
        raise HTTPException(status_code=409, detail=result.error)

    tool_result = result.tool_result
    return {
        "success": bool(tool_result and tool_result.success),
        "approved": result.approved,
        "blocked": result.blocked,
        "simulated": result.simulated,
        "execution_id": result.execution_id,
        "tool_result": {
            "tool_id": tool_result.tool_id if tool_result else None,
            "success": tool_result.success if tool_result else None,
            "data": tool_result.data if tool_result else None,
            "error": tool_result.error if tool_result else None,
        }
        if tool_result
        else None,
        "steps": [
            {
                "step_id": s.step_id,
                "tool_id": s.tool_id,
                "success": s.success,
                "error": s.error,
                "status": getattr(s, "status", None),
            }
            for s in result.step_results
        ],
    }
