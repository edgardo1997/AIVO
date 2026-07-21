import logging
from typing import Any, Dict, List, Optional
from sentinel.core.event_bus import EventBus
from sentinel.core.events import SentinelEvent
from sentinel.core import event_types

log = logging.getLogger(__name__)


class AutomationEngine:
    def __init__(self, event_bus: Optional[EventBus] = None):
        self._event_bus = event_bus
        self._rules: Dict[str, Dict[str, Any]] = {}

    def status(self) -> Dict[str, Any]:
        return {"rules": len(self._rules), "rule_ids": list(self._rules.keys())}

    def list_rules(self) -> List[Dict[str, Any]]:
        return [{"id": rid, **r} for rid, r in self._rules.items()]

    def add_rule(self, rule_id: str, condition: str, action: str, session_id: str = "", request_id: str = "") -> Dict[str, Any]:
        if rule_id in self._rules:
            return {"added": False, "error": "rule already exists"}
        self._rules[rule_id] = {"condition": condition, "action": action, "enabled": True, "trigger_count": 0}
        self._emit(event_types.AUTOMATION_RULE_ADDED, session_id, request_id, details={"rule_id": rule_id, "condition": condition, "action": action})
        log.info("Automation rule added: %s", rule_id)
        return {"added": True, "rule_id": rule_id}

    def remove_rule(self, rule_id: str, session_id: str = "", request_id: str = "") -> Dict[str, Any]:
        if rule_id not in self._rules:
            return {"removed": False, "error": "not found"}
        del self._rules[rule_id]
        self._emit(event_types.AUTOMATION_RULE_REMOVED, session_id, request_id, details={"rule_id": rule_id})
        log.info("Automation rule removed: %s", rule_id)
        return {"removed": True, "rule_id": rule_id}

    def trigger_rule(self, rule_id: str, session_id: str = "", request_id: str = "") -> Dict[str, Any]:
        if rule_id not in self._rules:
            return {"triggered": False, "error": "not found"}
        self._rules[rule_id]["trigger_count"] += 1
        self._emit(event_types.AUTOMATION_RULE_TRIGGERED, session_id, request_id, details={"rule_id": rule_id, "count": self._rules[rule_id]["trigger_count"]})
        log.info("Automation rule triggered: %s", rule_id)
        return {"triggered": True, "rule_id": rule_id, "count": self._rules[rule_id]["trigger_count"]}

    def execute_action(self, action: str, session_id: str = "", request_id: str = "") -> Dict[str, Any]:
        self._emit(event_types.AUTOMATION_ACTION_EXECUTED, session_id, request_id, details={"action": action})
        log.info("Automation action executed: %s", action)
        return {"executed": True, "action": action}

    def _emit(self, event_type: str, session_id: str, request_id: str, details: Optional[Dict] = None):
        if self._event_bus is None:
            return
        self._event_bus.emit(SentinelEvent.new(
            event_type=event_type,
            session_id=session_id or "system",
            request_id=request_id or "",
            component="automation_engine",
            details=details,
        ))
