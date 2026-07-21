import dataclasses
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict

log = logging.getLogger("sentinel.v1.execute")
router = APIRouter()


class ExecuteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_id: str
    params: Dict[str, Any] = {}
    dry_run: bool = False


class ExecuteResponse(BaseModel):
    success: bool
    data: Any = None
    error: Optional[str] = None
    requires_confirmation: bool = False
    action_id: Optional[str] = None
    duration_ms: Optional[float] = None
    pipeline: Optional[Dict[str, Any]] = None
    simulated: bool = False


class ConfirmExecuteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action_id: str
    approved: bool = True


@router.post("/confirm", response_model=ExecuteResponse)
async def confirm_tool(req: ConfirmExecuteRequest, request: Request):
    from modules import get_gateway
    from modules.auth import request_identity

    identity = request_identity(request).to_dict()
    result = await get_gateway().confirm(req.action_id, req.approved, identity)
    return ExecuteResponse(
        success=result.success,
        data=result.data,
        error=result.error,
        requires_confirmation=result.requires_confirmation,
        action_id=None,
        duration_ms=result.duration_ms,
    )


@router.post("/execute", response_model=ExecuteResponse)
async def execute_tool(req: ExecuteRequest, request: Request):
    from modules.sentinel_bridge import get_orchestrator
    from modules.auth import request_identity

    orch = get_orchestrator()
    identity = request_identity(request).to_dict()

    result = await orch.execute_direct(
        req.tool_id,
        dict(req.params),
        identity=identity,
        dry_run=req.dry_run,
    )

    if result.blocked:
        return ExecuteResponse(
            success=True,
            data={
                "blocked": True,
                "action_id": result.action_id,
                "simulation_summary": result.simulation_summary,
                "error": result.error,
            },
            simulated=True,
            requires_confirmation=True,
        )

    if result.error:
        return ExecuteResponse(
            success=False,
            data=None,
            error=result.error,
            simulated=result.simulated,
            requires_confirmation=False,
        )

    tr = result.tool_result
    if tr is None:
        raise HTTPException(status_code=500, detail="No tool result")

    return ExecuteResponse(
        success=tr.success,
        data=tr.data,
        error=tr.error,
        requires_confirmation=tr.requires_confirmation,
        action_id=(tr.data or {}).get("action_id") if isinstance(tr.data, dict) else None,
        duration_ms=tr.duration_ms,
        simulated=result.simulated,
        pipeline={
            "plan": dataclasses.asdict(result.plan) if result.plan else None,
            "decision": dataclasses.asdict(result.decision) if result.decision else None,
            "advisory": result.advisory.to_dict() if result.advisory else None,
        },
    )
