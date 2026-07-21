import asyncio
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class TriggerOperator(str, Enum):
    GT = "gt"
    LT = "lt"
    GTE = "gte"
    LTE = "lte"
    EQ = "eq"
    NEQ = "neq"


@dataclass
class TriggerCondition:
    metric: str
    operator: TriggerOperator
    value: float

    def evaluate(self, current_value: float) -> bool:
        if self.operator == TriggerOperator.GT:
            return current_value > self.value
        elif self.operator == TriggerOperator.LT:
            return current_value < self.value
        elif self.operator == TriggerOperator.GTE:
            return current_value >= self.value
        elif self.operator == TriggerOperator.LTE:
            return current_value <= self.value
        elif self.operator == TriggerOperator.EQ:
            return current_value == self.value
        elif self.operator == TriggerOperator.NEQ:
            return current_value != self.value
        return False

    def to_dict(self) -> Dict[str, Any]:
        return {"metric": self.metric, "operator": self.operator.value, "value": self.value}

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "TriggerCondition":
        return TriggerCondition(
            metric=data["metric"],
            operator=TriggerOperator(data["operator"]),
            value=data["value"],
        )


@dataclass
class TriggerAction:
    tool_id: str
    params: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {"tool_id": self.tool_id, "params": self.params}

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "TriggerAction":
        return TriggerAction(tool_id=data["tool_id"], params=data.get("params", {}))


@dataclass
class TriggerRule:
    id: str
    name: str
    description: str = ""
    conditions: List[TriggerCondition] = field(default_factory=list)
    action: Optional[TriggerAction] = None
    cooldown_seconds: int = 300
    enabled: bool = True
    last_fired: Optional[float] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def can_fire(self, now: Optional[float] = None) -> bool:
        if not self.enabled:
            return False
        if self.last_fired is None:
            return True
        elapsed = (now or time.time()) - self.last_fired
        return elapsed >= self.cooldown_seconds

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "conditions": [c.to_dict() for c in self.conditions],
            "action": self.action.to_dict() if self.action else None,
            "cooldown_seconds": self.cooldown_seconds,
            "enabled": self.enabled,
            "last_fired": self.last_fired,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "TriggerRule":
        conditions = [TriggerCondition.from_dict(c) for c in data.get("conditions", [])]
        action = TriggerAction.from_dict(data["action"]) if data.get("action") else None
        return TriggerRule(
            id=data["id"],
            name=data.get("name", data["id"]),
            description=data.get("description", ""),
            conditions=conditions,
            action=action,
            cooldown_seconds=data.get("cooldown_seconds", 300),
            enabled=data.get("enabled", True),
            last_fired=data.get("last_fired"),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )


@dataclass
class TriggerFireRecord:
    trigger_id: str
    condition_met: bool
    action_executed: bool
    result: Optional[str] = None
    timestamp: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trigger_id": self.trigger_id,
            "condition_met": self.condition_met,
            "action_executed": self.action_executed,
            "result": self.result,
            "timestamp": self.timestamp,
        }


class TriggerEngine:
    def __init__(self, execute_fn: Optional[Callable] = None):
        self._rules: Dict[str, TriggerRule] = {}
        self._history: List[TriggerFireRecord] = []
        self._execute_fn = execute_fn
        self._lock = threading.RLock()

    def add_rule(self, rule: TriggerRule, *, overwrite: bool = True) -> bool:
        with self._lock:
            if not overwrite and rule.id in self._rules:
                return False
            now = datetime.now(timezone.utc).isoformat()
            if not rule.created_at:
                rule.created_at = now
            rule.updated_at = now
            self._rules[rule.id] = rule
            return True

    def remove_rule(self, rule_id: str) -> None:
        with self._lock:
            if rule_id not in self._rules:
                raise KeyError(f"Trigger '{rule_id}' not found")
            del self._rules[rule_id]

    def get_rule(self, rule_id: str) -> Optional[TriggerRule]:
        with self._lock:
            return self._rules.get(rule_id)

    def list_rules(self) -> List[TriggerRule]:
        with self._lock:
            return list(self._rules.values())

    def update_rule(self, rule_id: str, **updates: Any) -> TriggerRule:
        with self._lock:
            rule = self._rules.get(rule_id)
            if rule is None:
                raise KeyError(f"Trigger '{rule_id}' not found")
            for key, value in updates.items():
                if key == "conditions" and isinstance(value, list):
                    rule.conditions = [TriggerCondition.from_dict(c) if isinstance(c, dict) else c for c in value]
                elif key == "action" and isinstance(value, dict):
                    rule.action = TriggerAction.from_dict(value)
                elif hasattr(rule, key):
                    setattr(rule, key, value)
            rule.updated_at = datetime.now(timezone.utc).isoformat()
            return rule

    def evaluate(self, metrics: Dict[str, float]) -> List[TriggerFireRecord]:
        now = time.time()
        pending: List[tuple[TriggerFireRecord, Optional[TriggerAction]]] = []
        with self._lock:
            for rule in self._rules.values():
                if not rule.can_fire(now):
                    continue
                all_met = all(
                    cond.metric in metrics and cond.evaluate(metrics[cond.metric]) for cond in rule.conditions
                )
                if not all_met:
                    continue
                rule.last_fired = now
                record = TriggerFireRecord(
                    trigger_id=rule.id,
                    condition_met=True,
                    action_executed=False,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
                pending.append((record, rule.action))

        fires: List[TriggerFireRecord] = []
        for record, action in pending:
                if action and self._execute_fn:
                    try:
                        if asyncio.iscoroutinefunction(self._execute_fn):
                            action_coro = self._execute_fn(action.tool_id, action.params)
                            try:
                                loop = asyncio.get_running_loop()
                            except RuntimeError:
                                asyncio.run(action_coro)
                            else:
                                loop.create_task(action_coro)
                        else:
                            self._execute_fn(action.tool_id, action.params)
                        record.action_executed = True
                        record.result = "executed"
                    except Exception as e:
                        record.result = f"error: {e}"
                        logger.error("Trigger %s action failed: %s", record.trigger_id, e)
                else:
                    record.action_executed = action is not None
                    record.result = "fired_no_action" if not action else "fired"
                fires.append(record)
        with self._lock:
            for record in fires:
                self._history.append(record)
        return fires

    def get_history(self, limit: int = 20) -> List[TriggerFireRecord]:
        with self._lock:
            return self._history[-limit:]

    def clear_history(self) -> None:
        with self._lock:
            self._history.clear()

    def count(self) -> int:
        with self._lock:
            return len(self._rules)
