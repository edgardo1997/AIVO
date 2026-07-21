from typing import Any, Dict, Optional
from sentinel.core.tool import Tool, ToolResult, ToolSpec

_CAT = "gaming"


class GamingStatusTool(Tool):
    def __init__(self, svc):
        self._svc = svc
    def spec(self) -> ToolSpec:
        return ToolSpec(id="gaming.status", name="Gaming Mode Status", description="Current gaming mode status", version="1.0.0", category=_CAT, parameters={"type": "object", "properties": {}, "required": []}, required_permissions=["system.read"])
    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        return ToolResult.ok(data=self._svc.status(), tool_id="gaming.status")


class GamingActivateTool(Tool):
    def __init__(self, svc):
        self._svc = svc
    def spec(self) -> ToolSpec:
        return ToolSpec(id="gaming.activate", name="Activate Gaming Mode", description="Activate gaming mode", version="1.0.0", category=_CAT, parameters={"type": "object", "properties": {"game": {"type": "string", "description": "Optional game name"}}, "required": []}, required_permissions=["system.write"])
    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        sid = (context or {}).get("session_id", "")
        rid = (context or {}).get("request_id", "")
        return ToolResult.ok(data=self._svc.activate(game=params.get("game", ""), session_id=sid, request_id=rid), tool_id="gaming.activate")


class GamingDeactivateTool(Tool):
    def __init__(self, svc):
        self._svc = svc
    def spec(self) -> ToolSpec:
        return ToolSpec(id="gaming.deactivate", name="Deactivate Gaming Mode", description="Deactivate gaming mode", version="1.0.0", category=_CAT, parameters={"type": "object", "properties": {}, "required": []}, required_permissions=["system.write"])
    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        sid = (context or {}).get("session_id", "")
        rid = (context or {}).get("request_id", "")
        return ToolResult.ok(data=self._svc.deactivate(session_id=sid, request_id=rid), tool_id="gaming.deactivate")


class GamingDetectTool(Tool):
    def __init__(self, svc):
        self._svc = svc
    def spec(self) -> ToolSpec:
        return ToolSpec(id="gaming.detect", name="Detect Game", description="Report a game for gaming mode optimization", version="1.0.0", category=_CAT, parameters={"type": "object", "properties": {"game": {"type": "string", "description": "Game name"}}, "required": ["game"]}, required_permissions=["system.read"])
    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        sid = (context or {}).get("session_id", "")
        rid = (context or {}).get("request_id", "")
        return ToolResult.ok(data=self._svc.detect_game(params.get("game", ""), session_id=sid, request_id=rid), tool_id="gaming.detect")
