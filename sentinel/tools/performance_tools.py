from typing import Any, Dict, Optional
from sentinel.core.tool import Tool, ToolResult, ToolSpec

_CAT = "performance"


class PerformanceStatusTool(Tool):
    def __init__(self, engine):
        self._engine = engine
    def spec(self) -> ToolSpec:
        return ToolSpec(id="performance.status", name="Performance Status", description="Current performance engine status", version="1.0.0", category=_CAT, parameters={"type": "object", "properties": {}, "required": []}, required_permissions=["system.read"])
    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        return ToolResult.ok(data=self._engine.status(), tool_id="performance.status")


class PerformanceSetProfileTool(Tool):
    def __init__(self, engine):
        self._engine = engine
    def spec(self) -> ToolSpec:
        return ToolSpec(id="performance.profile.set", name="Set Performance Profile", description="Set performance profile (balanced, performance, power_saver)", version="1.0.0", category=_CAT, parameters={"type": "object", "properties": {"profile": {"type": "string", "enum": ["balanced", "performance", "power_saver"]}}, "required": ["profile"]}, required_permissions=["system.write"])
    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        sid = (context or {}).get("session_id", "")
        rid = (context or {}).get("request_id", "")
        return ToolResult.ok(data=self._engine.set_profile(params.get("profile", "balanced"), session_id=sid, request_id=rid), tool_id="performance.profile.set")


class PerformanceProfilingStartTool(Tool):
    def __init__(self, engine):
        self._engine = engine
    def spec(self) -> ToolSpec:
        return ToolSpec(id="performance.profiling.start", name="Start Profiling", description="Start performance profiling", version="1.0.0", category=_CAT, parameters={"type": "object", "properties": {}, "required": []}, required_permissions=["system.write"])
    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        sid = (context or {}).get("session_id", "")
        rid = (context or {}).get("request_id", "")
        return ToolResult.ok(data=self._engine.start_profiling(session_id=sid, request_id=rid), tool_id="performance.profiling.start")


class PerformanceProfilingStopTool(Tool):
    def __init__(self, engine):
        self._engine = engine
    def spec(self) -> ToolSpec:
        return ToolSpec(id="performance.profiling.stop", name="Stop Profiling", description="Stop performance profiling", version="1.0.0", category=_CAT, parameters={"type": "object", "properties": {}, "required": []}, required_permissions=["system.write"])
    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        sid = (context or {}).get("session_id", "")
        rid = (context or {}).get("request_id", "")
        return ToolResult.ok(data=self._engine.stop_profiling(session_id=sid, request_id=rid), tool_id="performance.profiling.stop")
