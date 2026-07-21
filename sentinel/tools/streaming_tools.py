from typing import Any, Dict, Optional
from sentinel.core.tool import Tool, ToolResult, ToolSpec

_CAT = "streaming"


class StreamingStatusTool(Tool):
    def __init__(self, svc):
        self._svc = svc
    def spec(self) -> ToolSpec:
        return ToolSpec(id="streaming.status", name="Streaming Mode Status", description="Current streaming mode status", version="1.0.0", category=_CAT, parameters={"type": "object", "properties": {}, "required": []}, required_permissions=["system.read"])
    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        return ToolResult.ok(data=self._svc.status(), tool_id="streaming.status")


class StreamingActivateTool(Tool):
    def __init__(self, svc):
        self._svc = svc
    def spec(self) -> ToolSpec:
        return ToolSpec(id="streaming.activate", name="Activate Streaming Mode", description="Activate streaming mode for a platform", version="1.0.0", category=_CAT, parameters={"type": "object", "properties": {"platform": {"type": "string", "description": "Streaming platform (twitch, youtube, etc)"}}, "required": []}, required_permissions=["system.write"])
    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        sid = (context or {}).get("session_id", "")
        rid = (context or {}).get("request_id", "")
        return ToolResult.ok(data=self._svc.activate(platform=params.get("platform", ""), session_id=sid, request_id=rid), tool_id="streaming.activate")


class StreamingDeactivateTool(Tool):
    def __init__(self, svc):
        self._svc = svc
    def spec(self) -> ToolSpec:
        return ToolSpec(id="streaming.deactivate", name="Deactivate Streaming Mode", description="Deactivate streaming mode", version="1.0.0", category=_CAT, parameters={"type": "object", "properties": {}, "required": []}, required_permissions=["system.write"])
    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        sid = (context or {}).get("session_id", "")
        rid = (context or {}).get("request_id", "")
        return ToolResult.ok(data=self._svc.deactivate(session_id=sid, request_id=rid), tool_id="streaming.deactivate")


class StreamingStartTool(Tool):
    def __init__(self, svc):
        self._svc = svc
    def spec(self) -> ToolSpec:
        return ToolSpec(id="streaming.start", name="Start Stream", description="Start a live stream", version="1.0.0", category=_CAT, parameters={"type": "object", "properties": {}, "required": []}, required_permissions=["system.write"])
    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        sid = (context or {}).get("session_id", "")
        rid = (context or {}).get("request_id", "")
        return ToolResult.ok(data=self._svc.start_stream(session_id=sid, request_id=rid), tool_id="streaming.start")


class StreamingStopTool(Tool):
    def __init__(self, svc):
        self._svc = svc
    def spec(self) -> ToolSpec:
        return ToolSpec(id="streaming.stop", name="Stop Stream", description="Stop the live stream", version="1.0.0", category=_CAT, parameters={"type": "object", "properties": {}, "required": []}, required_permissions=["system.write"])
    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        sid = (context or {}).get("session_id", "")
        rid = (context or {}).get("request_id", "")
        return ToolResult.ok(data=self._svc.stop_stream(session_id=sid, request_id=rid), tool_id="streaming.stop")
