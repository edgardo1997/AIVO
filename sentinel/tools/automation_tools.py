from typing import Any, Dict, Optional
from sentinel.core.tool import Tool, ToolResult, ToolSpec

_CAT = "automation"


class AutomationListRulesTool(Tool):
    def __init__(self, svc):
        self._svc = svc
    def spec(self) -> ToolSpec:
        return ToolSpec(id="automation.rules.list", name="List Automation Rules", description="List all automation rules", version="1.0.0", category=_CAT, parameters={"type": "object", "properties": {}, "required": []}, required_permissions=["system.read"])
    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        return ToolResult.ok(data={"rules": self._svc.list_rules()}, tool_id="automation.rules.list")


class AutomationAddRuleTool(Tool):
    def __init__(self, svc):
        self._svc = svc
    def spec(self) -> ToolSpec:
        return ToolSpec(id="automation.rules.add", name="Add Automation Rule", description="Add a new automation rule", version="1.0.0", category=_CAT, parameters={"type": "object", "properties": {"rule_id": {"type": "string"}, "condition": {"type": "string", "description": "Trigger condition"}, "action": {"type": "string", "description": "Action to execute"}}, "required": ["rule_id", "condition", "action"]}, required_permissions=["system.write"])
    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        sid = (context or {}).get("session_id", "")
        rid = (context or {}).get("request_id", "")
        return ToolResult.ok(data=self._svc.add_rule(params["rule_id"], params.get("condition", ""), params.get("action", ""), session_id=sid, request_id=rid), tool_id="automation.rules.add")


class AutomationRemoveRuleTool(Tool):
    def __init__(self, svc):
        self._svc = svc
    def spec(self) -> ToolSpec:
        return ToolSpec(id="automation.rules.remove", name="Remove Automation Rule", description="Remove an automation rule", version="1.0.0", category=_CAT, parameters={"type": "object", "properties": {"rule_id": {"type": "string"}}, "required": ["rule_id"]}, required_permissions=["system.write"])
    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        sid = (context or {}).get("session_id", "")
        rid = (context or {}).get("request_id", "")
        return ToolResult.ok(data=self._svc.remove_rule(params["rule_id"], session_id=sid, request_id=rid), tool_id="automation.rules.remove")


class AutomationTriggerRuleTool(Tool):
    def __init__(self, svc):
        self._svc = svc
    def spec(self) -> ToolSpec:
        return ToolSpec(id="automation.trigger", name="Trigger Automation Rule", description="Manually trigger an automation rule", version="1.0.0", category=_CAT, parameters={"type": "object", "properties": {"rule_id": {"type": "string"}, "action": {"type": "string", "description": "Optional action to execute alongside"}}, "required": ["rule_id"]}, required_permissions=["system.write"])
    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        sid = (context or {}).get("session_id", "")
        rid = (context or {}).get("request_id", "")
        res = self._svc.trigger_rule(params["rule_id"], session_id=sid, request_id=rid)
        if params.get("action"):
            res["action_result"] = self._svc.execute_action(params["action"], session_id=sid, request_id=rid)
        return ToolResult.ok(data=res, tool_id="automation.trigger")
