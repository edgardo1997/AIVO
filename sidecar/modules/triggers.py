import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter

from sentinel.core.trigger import TriggerRule, TriggerCondition, TriggerAction, TriggerEngine, TriggerFireRecord
from repositories.database import DatabaseManager

log = logging.getLogger("sentinel.triggers")
router = APIRouter()

_engine: Optional[TriggerEngine] = None
_db: Optional[DatabaseManager] = None


def get_engine() -> TriggerEngine:
    global _engine
    if _engine is None:
        _engine = TriggerEngine()
    return _engine


def wire_dependencies(db: DatabaseManager) -> None:
    global _db, _engine
    _db = db
    _engine = get_engine()
    _load_from_db()


def _load_from_db() -> None:
    if not _db:
        return
    rows = _db.fetchall("SELECT * FROM triggers")
    for row in rows:
        try:
            conditions_data = json.loads(row.get("conditions", "[]"))
            conditions = [TriggerCondition.from_dict(c) for c in conditions_data]
            action_data = row.get("action")
            action = TriggerAction.from_dict(json.loads(action_data)) if action_data else None
            rule = TriggerRule(
                id=row["trigger_id"],
                name=row["name"],
                description=row.get("description", ""),
                conditions=conditions,
                action=action,
                cooldown_seconds=row.get("cooldown_seconds", 300),
                enabled=bool(row.get("enabled", 1)),
                last_fired=row.get("last_fired"),
                created_at=row.get("created_at"),
                updated_at=row.get("updated_at"),
            )
            _engine.add_rule(rule)
        except Exception as e:
            log.error("Failed to load trigger '%s': %s", row.get("trigger_id"), e)
    log.info("Loaded %d triggers from database", _engine.count())


def _save_rule(rule: TriggerRule) -> None:
    if not _db:
        return
    now = datetime.now(timezone.utc).isoformat()
    _db.execute(
        """INSERT OR REPLACE INTO triggers
           (trigger_id, name, description, conditions, action, cooldown_seconds, enabled, last_fired, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, COALESCE(?, datetime('now')), ?)""",
        (
            rule.id,
            rule.name,
            rule.description,
            json.dumps([c.to_dict() for c in rule.conditions]),
            json.dumps(rule.action.to_dict()) if rule.action else None,
            rule.cooldown_seconds,
            1 if rule.enabled else 0,
            rule.last_fired,
            rule.created_at,
            now,
        ),
    )
    _db.commit()


def _delete_rule_db(rule_id: str) -> None:
    if not _db:
        return
    _db.execute("DELETE FROM triggers WHERE trigger_id = ?", (rule_id,))
    _db.commit()


def _save_history(record: TriggerFireRecord) -> None:
    if not _db:
        return
    _db.execute(
        "INSERT INTO trigger_history (trigger_id, condition_met, action_executed, result, timestamp) VALUES (?, ?, ?, ?, ?)",
        (record.trigger_id, 1 if record.condition_met else 0, 1 if record.action_executed else 0, record.result, record.timestamp),
    )
    _db.commit()


# --- Hook the engine's add/remove to persist ---
def _wrap_engine_for_persistence() -> None:
    engine = get_engine()

    orig_add = engine.add_rule
    def wrapped_add(rule: TriggerRule) -> None:
        orig_add(rule)
        _save_rule(rule)
    engine.add_rule = wrapped_add

    orig_remove = engine.remove_rule
    def wrapped_remove(rule_id: str) -> None:
        orig_remove(rule_id)
        _delete_rule_db(rule_id)
    engine.remove_rule = wrapped_remove

    orig_evaluate = engine.evaluate
    def wrapped_evaluate(metrics: Dict[str, float]) -> List[TriggerFireRecord]:
        fires = orig_evaluate(metrics)
        for rec in fires:
            _save_history(rec)
            if rec.action_executed:
                rule = engine.get_rule(rec.trigger_id)
                if rule:
                    _save_rule(rule)
        return fires
    engine.evaluate = wrapped_evaluate

    orig_update = engine.update_rule
    def wrapped_update(rule_id: str, **updates: Any) -> TriggerRule:
        rule = orig_update(rule_id, **updates)
        _save_rule(rule)
        return rule
    engine.update_rule = wrapped_update


wrap_done = False


def ensure_wired() -> None:
    global wrap_done
    if not wrap_done:
        _wrap_engine_for_persistence()
        wrap_done = True


# --- API endpoints ---

@router.get("/triggers")
def list_triggers():
    ensure_wired()
    engine = get_engine()
    return {"triggers": [r.to_dict() for r in engine.list_rules()], "total": engine.count()}


@router.get("/triggers/{trigger_id}")
def get_trigger(trigger_id: str):
    ensure_wired()
    engine = get_engine()
    rule = engine.get_rule(trigger_id)
    if not rule:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Trigger '{trigger_id}' not found")
    return {"trigger": rule.to_dict()}


@router.post("/triggers", status_code=201)
def create_trigger(body: dict):
    ensure_wired()
    engine = get_engine()
    rule_id = body.get("id", "")
    if not rule_id:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="id is required")
    if engine.get_rule(rule_id):
        from fastapi import HTTPException
        raise HTTPException(status_code=409, detail=f"Trigger '{rule_id}' already exists")
    conditions = [TriggerCondition.from_dict(c) for c in body.get("conditions", [])]
    action_data = body.get("action")
    action = TriggerAction.from_dict(action_data) if action_data else None
    rule = TriggerRule(
        id=rule_id,
        name=body.get("name", rule_id),
        description=body.get("description", ""),
        conditions=conditions,
        action=action,
        cooldown_seconds=body.get("cooldown_seconds", 300),
        enabled=body.get("enabled", True),
    )
    engine.add_rule(rule)
    log.info("Trigger '%s' created via API", rule_id)
    return {"status": "created", "trigger_id": rule_id}


@router.patch("/triggers/{trigger_id}")
def update_trigger(trigger_id: str, body: dict):
    ensure_wired()
    engine = get_engine()
    rule = engine.get_rule(trigger_id)
    if not rule:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Trigger '{trigger_id}' not found")
    updates = {}
    if "name" in body:
        updates["name"] = body["name"]
    if "description" in body:
        updates["description"] = body["description"]
    if "conditions" in body:
        updates["conditions"] = body["conditions"]
    if "action" in body:
        updates["action"] = body["action"]
    if "cooldown_seconds" in body:
        updates["cooldown_seconds"] = body["cooldown_seconds"]
    if "enabled" in body:
        updates["enabled"] = body["enabled"]
    engine.update_rule(trigger_id, **updates)
    return {"status": "updated", "trigger_id": trigger_id}


@router.delete("/triggers/{trigger_id}")
def delete_trigger(trigger_id: str):
    ensure_wired()
    engine = get_engine()
    try:
        engine.remove_rule(trigger_id)
        return {"status": "deleted", "trigger_id": trigger_id}
    except KeyError:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Trigger '{trigger_id}' not found")


@router.get("/triggers/{trigger_id}/history")
def get_trigger_history(trigger_id: str, limit: int = 20):
    if not _db:
        return {"history": [], "total": 0}
    rows = _db.fetchall(
        "SELECT * FROM trigger_history WHERE trigger_id = ? ORDER BY timestamp DESC LIMIT ?",
        (trigger_id, limit),
    )
    return {"history": rows, "total": len(rows)}


@router.get("/triggers/history/all")
def get_all_history(limit: int = 50):
    if not _db:
        return {"history": [], "total": 0}
    rows = _db.fetchall(
        "SELECT * FROM trigger_history ORDER BY timestamp DESC LIMIT ?",
        (limit,),
    )
    return {"history": rows, "total": len(rows)}


@router.post("/triggers/{trigger_id}/evaluate")
def evaluate_trigger(trigger_id: str, body: dict):
    ensure_wired()
    engine = get_engine()
    rule = engine.get_rule(trigger_id)
    if not rule:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Trigger '{trigger_id}' not found")
    metrics = body.get("metrics", {})
    fires = engine.evaluate(metrics)
    return {"fires": [f.to_dict() for f in fires], "total_fired": len(fires)}
