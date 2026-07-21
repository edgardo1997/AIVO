import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from sentinel.core.trigger import TriggerRule, TriggerCondition, TriggerAction, TriggerEngine, TriggerOperator
from repositories.database import DatabaseManager

log = logging.getLogger("sentinel.v1.triggers")
router = APIRouter()

_db: Optional[DatabaseManager] = None


def setup(engine: TriggerEngine, db: DatabaseManager) -> None:
    global _db
    _db = db


class TriggerConditionModel(BaseModel):
    metric: str
    operator: str
    value: float


class TriggerActionModel(BaseModel):
    tool_id: str
    params: Dict[str, Any] = {}


class CreateTriggerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    name: str = ""
    description: str = ""
    conditions: List[TriggerConditionModel]
    action: Optional[TriggerActionModel] = None
    cooldown_seconds: int = 300
    enabled: bool = True


class UpdateTriggerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Optional[str] = None
    description: Optional[str] = None
    conditions: Optional[List[TriggerConditionModel]] = None
    action: Optional[TriggerActionModel] = None
    cooldown_seconds: Optional[int] = None
    enabled: Optional[bool] = None


class TriggerInfoResponse(BaseModel):
    id: str
    name: str
    description: str = ""
    conditions: List[dict] = []
    action: Optional[dict] = None
    cooldown_seconds: int = 300
    enabled: bool = True
    last_fired: Optional[float] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class TriggerHistoryResponse(BaseModel):
    id: int
    trigger_id: str
    condition_met: bool
    action_executed: bool
    result: Optional[str] = None
    timestamp: Optional[str] = None


@router.get("/triggers", response_model=dict)
async def list_triggers(request: Request):
    from modules import get_gateway
    from modules.auth import request_identity

    identity = request_identity(request).to_dict()
    result = await get_gateway().execute("trigger.list", {}, {"identity": identity})
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)
    return result.data or {"triggers": [], "total": 0}


@router.get("/triggers/history", response_model=dict)
async def get_all_history(limit: int = 50):
    if not _db:
        return {"history": [], "total": 0}
    rows = _db.fetchall(
        "SELECT * FROM trigger_history ORDER BY timestamp DESC LIMIT ?",
        (limit,),
    )
    return {"history": rows, "total": len(rows)}


@router.get("/triggers/{trigger_id}", response_model=dict)
async def get_trigger(trigger_id: str, request: Request):
    from modules import get_gateway
    from modules.auth import request_identity

    identity = request_identity(request).to_dict()
    result = await get_gateway().execute("trigger.list", {}, {"identity": identity})
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)
    triggers = (result.data or {}).get("triggers", [])
    for t in triggers:
        if t.get("id") == trigger_id:
            return {"trigger": t}
    raise HTTPException(status_code=404, detail=f"Trigger '{trigger_id}' not found")


@router.post("/triggers", status_code=201)
async def create_trigger(body: CreateTriggerRequest, request: Request):
    from modules import get_gateway
    from modules.auth import request_identity

    identity = request_identity(request).to_dict()
    params = body.model_dump()
    result = await get_gateway().execute("trigger.create", params, {"identity": identity})
    if not result.success:
        if "already exists" in (result.error or ""):
            raise HTTPException(status_code=409, detail=result.error)
        raise HTTPException(status_code=400, detail=result.error)
    return {"status": "created", "trigger_id": body.id}


@router.patch("/triggers/{trigger_id}")
async def update_trigger(trigger_id: str, body: UpdateTriggerRequest, request: Request):
    from modules import get_gateway
    from modules.auth import request_identity

    identity = request_identity(request).to_dict()
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    params = {"id": trigger_id, **updates}
    result = await get_gateway().execute("trigger.update", params, {"identity": identity})
    if not result.success:
        if "not found" in (result.error or ""):
            raise HTTPException(status_code=404, detail=result.error)
        raise HTTPException(status_code=400, detail=result.error)
    return {"status": "updated", "trigger_id": trigger_id}


@router.delete("/triggers/{trigger_id}")
async def delete_trigger(trigger_id: str, request: Request):
    from modules import get_gateway
    from modules.auth import request_identity

    identity = request_identity(request).to_dict()
    result = await get_gateway().execute("trigger.delete", {"id": trigger_id}, {"identity": identity})
    if not result.success:
        if "not found" in (result.error or ""):
            raise HTTPException(status_code=404, detail=result.error)
        raise HTTPException(status_code=400, detail=result.error)
    return {"status": "deleted", "trigger_id": trigger_id}


@router.get("/triggers/{trigger_id}/history", response_model=dict)
async def get_trigger_history(trigger_id: str, limit: int = 20):
    if not _db:
        return {"history": [], "total": 0}
    rows = _db.fetchall(
        "SELECT * FROM trigger_history WHERE trigger_id = ? ORDER BY timestamp DESC LIMIT ?",
        (trigger_id, limit),
    )
    return {"history": rows, "total": len(rows)}
