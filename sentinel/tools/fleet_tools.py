from typing import Any, Dict
from sentinel.core.tool import Tool, ToolResult, ToolSpec


class FleetStatusTool(Tool):
    def __init__(self, service):
        self._svc = service

    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="fleet.status",
            name="Fleet Status",
            description="Get fleet/remote access status",
            version="0.1.0",
            parameters={},
            required_permissions=["fleet.read"],
            timeout_seconds=10,
            category="fleet",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            result = self._svc.get_status()
            result["api_url"] = f"http://{result.get('local_ip', '127.0.0.1')}:8765"
            result["paired"] = bool(self._svc.repo.load().get("paired", False)) if hasattr(self._svc, "repo") else False
            return ToolResult.ok(data=result, tool_id="fleet.status")
        except Exception as e:
            return ToolResult.fail(error=str(e), tool_id="fleet.status")


class FleetGeneratePairingTool(Tool):
    def __init__(self, service):
        self._svc = service

    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="fleet.generate_pairing",
            name="Generate Pairing Token",
            description="Generate a new pairing token for remote access",
            version="0.1.0",
            parameters={},
            required_permissions=["fleet.admin"],
            timeout_seconds=10,
            category="fleet",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            result = self._svc.generate_pairing()
            return ToolResult.ok(data=result, tool_id="fleet.generate_pairing")
        except Exception as e:
            return ToolResult.fail(error=str(e), tool_id="fleet.generate_pairing")


class FleetRevokePairingTool(Tool):
    def __init__(self, service):
        self._svc = service

    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="fleet.revoke_pairing",
            name="Revoke Pairing Token",
            description="Revoke the current pairing token",
            version="0.1.0",
            parameters={},
            required_permissions=["fleet.admin"],
            timeout_seconds=10,
            category="fleet",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            result = self._svc.revoke_pairing()
            return ToolResult.ok(data=result, tool_id="fleet.revoke_pairing")
        except Exception as e:
            return ToolResult.fail(error=str(e), tool_id="fleet.revoke_pairing")


class FleetToggleRemoteTool(Tool):
    def __init__(self, service):
        self._svc = service

    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="fleet.toggle_remote",
            name="Toggle Remote Access",
            description="Enable or disable remote access",
            version="0.1.0",
            parameters={},
            required_permissions=["fleet.admin"],
            timeout_seconds=10,
            category="fleet",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            result = self._svc.toggle_remote()
            return ToolResult.ok(data=result, tool_id="fleet.toggle_remote")
        except Exception as e:
            return ToolResult.fail(error=str(e), tool_id="fleet.toggle_remote")


class FleetQrTool(Tool):
    def __init__(self, service):
        self._svc = service

    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="fleet.qr",
            name="Fleet QR Data",
            description="Get QR code data for pairing",
            version="0.1.0",
            parameters={},
            required_permissions=["fleet.read"],
            timeout_seconds=10,
            category="fleet",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            result = self._svc.get_qr_data()
            return ToolResult.ok(data=result, tool_id="fleet.qr")
        except Exception as e:
            return ToolResult.fail(error=str(e), tool_id="fleet.qr")
