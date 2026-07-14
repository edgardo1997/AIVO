import asyncio
import json
import logging
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

    def add_rule(self, rule: TriggerRule) -> None:
        now = datetime.now(timezone.utc).isoformat()
        if not rule.created_at:
            rule.created_at = now
        rule.updated_at = now
        self._rules[rule.id] = rule

    def remove_rule(self, rule_id: str) -> None:
        if rule_id not in self._rules:
            raise KeyError(f"Trigger '{rule_id}' not found")
        del self._rules[rule_id]

    def get_rule(self, rule_id: str) -> Optional[TriggerRule]:
        return self._rules.get(rule_id)

    def list_rules(self) -> List[TriggerRule]:
        return list(self._rules.values())

    def update_rule(self, rule_id: str, **updates: Any) -> TriggerRule:
        rule = self.get_rule(rule_id)
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
        fires: List[TriggerFireRecord] = []
        for rule in self._rules.values():
            if not rule.can_fire(now):
                continue
            all_met = True
            for cond in rule.conditions:
                current = metrics.get(cond.metric)
                if current is None:
                    all_met = False
                    break
                if not cond.evaluate(current):
                    all_met = False
                    break
            if all_met:
                rule.last_fired = now
                record = TriggerFireRecord(
                    trigger_id=rule.id,
                    condition_met=True,
                    action_executed=False,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
                if rule.action and self._execute_fn:
                    try:
                        if asyncio.iscoroutinefunction(self._execute_fn):
                            asyncio.create_task(self._execute_fn(rule.action.tool_id, rule.action.params))
                        else:
                            self._execute_fn(rule.action.tool_id, rule.action.params)
                        record.action_executed = True
                        record.result = "executed"
                    except Exception as e:
                        record.result = f"error: {e}"
                        logger.error("Trigger %s action failed: %s", rule.id, e)
                else:
                    record.action_executed = rule.action is not None
                    record.result = "fired_no_action" if not rule.action else "fired"
                fires.append(record)
                self._history.append(record)
        return fires

    def get_history(self, limit: int = 20) -> List[TriggerFireRecord]:
        return self._history[-limit:]

    def clear_history(self) -> None:
        self._history.clear()

    def count(self) -> int:
        return len(self._rules)
