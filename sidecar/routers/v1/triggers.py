import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from sentinel.core.trigger import TriggerRule, TriggerCondition, TriggerAction, TriggerEngine, TriggerOperator
from repositories.database import DatabaseManager

log = logging.getLogger("sentinel.v1.triggers")
router = APIRouter()

# These are injected from main.py after module init
_engine: Optional[TriggerEngine] = None
_db: Optional[DatabaseManager] = None


def setup(engine: TriggerEngine, db: DatabaseManager) -> None:
    global _engine, _db
    _engine = engine
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
async def list_triggers():
    if not _engine:
        raise HTTPException(status_code=500, detail="Trigger engine not available")
    return {"triggers": [r.to_dict() for r in _engine.list_rules()], "total": _engine.count()}


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
async def get_trigger(trigger_id: str):
    if not _engine:
        raise HTTPException(status_code=500, detail="Trigger engine not available")
    rule = _engine.get_rule(trigger_id)
    if not rule:
        raise HTTPException(status_code=404, detail=f"Trigger '{trigger_id}' not found")
    return {"trigger": rule.to_dict()}


@router.post("/triggers", status_code=201)
async def create_trigger(body: CreateTriggerRequest):
    if not _engine:
        raise HTTPException(status_code=500, detail="Trigger engine not available")
    if _engine.get_rule(body.id):
        raise HTTPException(status_code=409, detail=f"Trigger '{body.id}' already exists")
    conditions = [
        TriggerCondition(metric=c.metric, operator=TriggerOperator(c.operator), value=c.value) for c in body.conditions
    ]
    action = TriggerAction(tool_id=body.action.tool_id, params=body.action.params) if body.action else None
    rule = TriggerRule(
        id=body.id,
        name=body.name or body.id,
        description=body.description or "",
        conditions=conditions,
        action=action,
        cooldown_seconds=body.cooldown_seconds,
        enabled=body.enabled,
    )
    _engine.add_rule(rule)
    log.info("Trigger '%s' created via v1 API", body.id)
    return {"status": "created", "trigger_id": body.id}


@router.patch("/triggers/{trigger_id}")
async def update_trigger(trigger_id: str, body: UpdateTriggerRequest):
    if not _engine:
        raise HTTPException(status_code=500, detail="Trigger engine not available")
    rule = _engine.get_rule(trigger_id)
    if not rule:
        raise HTTPException(status_code=404, detail=f"Trigger '{trigger_id}' not found")
    updates = {}
    for field in ("name", "description", "cooldown_seconds", "enabled"):
        val = getattr(body, field, None)
        if val is not None:
            updates[field] = val
    if body.conditions is not None:
        updates["conditions"] = [
            {"metric": c.metric, "operator": c.operator, "value": c.value} for c in body.conditions
        ]
    if body.action is not None:
        updates["action"] = {"tool_id": body.action.tool_id, "params": body.action.params}
    _engine.update_rule(trigger_id, **updates)
    return {"status": "updated", "trigger_id": trigger_id}


@router.delete("/triggers/{trigger_id}")
async def delete_trigger(trigger_id: str):
    if not _engine:
        raise HTTPException(status_code=500, detail="Trigger engine not available")
    try:
        _engine.remove_rule(trigger_id)
        return {"status": "deleted", "trigger_id": trigger_id}
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Trigger '{trigger_id}' not found")


@router.get("/triggers/{trigger_id}/history", response_model=dict)
async def get_trigger_history(trigger_id: str, limit: int = 20):
    if not _db:
        return {"history": [], "total": 0}
    rows = _db.fetchall(
        "SELECT * FROM trigger_history WHERE trigger_id = ? ORDER BY timestamp DESC LIMIT ?",
        (trigger_id, limit),
    )
    return {"history": rows, "total": len(rows)}
