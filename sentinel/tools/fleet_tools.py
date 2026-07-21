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
            version="1.0.0",
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
            version="1.0.0",
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
            version="1.0.0",
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
            version="1.0.0",
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
            version="1.0.0",
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


class FleetListDevicesTool(Tool):
    def __init__(self, service):
        self._svc = service

    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="fleet.list_devices",
            name="List Fleet Devices",
            description="List all registered devices in the fleet",
            version="1.0.0",
            parameters={},
            required_permissions=["fleet.read"],
            timeout_seconds=10,
            category="fleet",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            devices = self._svc.list_devices()
            return ToolResult.ok(data={"devices": devices}, tool_id="fleet.list_devices")
        except Exception as e:
            return ToolResult.fail(error=str(e), tool_id="fleet.list_devices")


class FleetRegisterDeviceTool(Tool):
    def __init__(self, service):
        self._svc = service

    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="fleet.register_device",
            name="Register Fleet Device",
            description="Register a new device in the fleet",
            version="1.0.0",
            parameters={
                "type": "object",
                "properties": {
                    "device_id": {"type": "string", "description": "Unique device identifier"},
                    "name": {"type": "string", "description": "Human-readable device name"},
                    "device_type": {"type": "string", "description": "Device type (node, mobile, etc.)"},
                    "os": {"type": "string", "description": "Operating system string"},
                    "version": {"type": "string", "description": "Software version"},
                    "ip": {"type": "string", "description": "IP address"},
                    "port": {"type": "integer", "description": "API port"},
                },
                "required": ["device_id", "name"],
            },
            required_permissions=["fleet.admin"],
            timeout_seconds=10,
            category="fleet",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            result = self._svc.register_device(params)
            return ToolResult.ok(data=result, tool_id="fleet.register_device")
        except Exception as e:
            return ToolResult.fail(error=str(e), tool_id="fleet.register_device")


class FleetDeleteDeviceTool(Tool):
    def __init__(self, service):
        self._svc = service

    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="fleet.delete_device",
            name="Delete Fleet Device",
            description="Remove a device from the fleet registry",
            version="1.0.0",
            parameters={
                "type": "object",
                "properties": {
                    "device_id": {"type": "string", "description": "Device ID to remove"},
                },
                "required": ["device_id"],
            },
            required_permissions=["fleet.admin"],
            timeout_seconds=10,
            category="fleet",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            result = self._svc.delete_device(params.get("device_id", ""))
            return ToolResult.ok(data=result, tool_id="fleet.delete_device")
        except Exception as e:
            return ToolResult.fail(error=str(e), tool_id="fleet.delete_device")


class FleetSyncPushTool(Tool):
    def __init__(self, service):
        self._svc = service

    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="fleet.sync_push",
            name="Sync Push to Peer",
            description="Push local config and device data to a remote peer",
            version="1.0.0",
            parameters={
                "type": "object",
                "properties": {
                    "peer_url": {"type": "string", "description": "Remote peer base URL (e.g. http://192.168.1.100:8765)"},
                    "token": {"type": "string", "description": "Pairing token for authentication"},
                    "config_keys": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of config keys to sync (fleet, devices, config)",
                    },
                },
                "required": ["peer_url", "token"],
            },
            required_permissions=["fleet.admin"],
            timeout_seconds=60,
            category="fleet",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            result = self._svc.sync_push(params.get("peer_url", ""), params.get("token", ""), params.get("config_keys"))
            return ToolResult.ok(data=result, tool_id="fleet.sync_push")
        except Exception as e:
            return ToolResult.fail(error=str(e), tool_id="fleet.sync_push")


class FleetSyncPullTool(Tool):
    def __init__(self, service):
        self._svc = service

    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="fleet.sync_pull",
            name="Sync Pull from Peer",
            description="Pull config and device data from a remote peer",
            version="1.0.0",
            parameters={
                "type": "object",
                "properties": {
                    "peer_url": {"type": "string", "description": "Remote peer base URL"},
                    "token": {"type": "string", "description": "Pairing token for authentication"},
                    "config_keys": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of config keys to sync",
                    },
                },
                "required": ["peer_url", "token"],
            },
            required_permissions=["fleet.admin"],
            timeout_seconds=60,
            category="fleet",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            result = self._svc.sync_pull(params.get("peer_url", ""), params.get("token", ""), params.get("config_keys"))
            return ToolResult.ok(data=result, tool_id="fleet.sync_pull")
        except Exception as e:
            return ToolResult.fail(error=str(e), tool_id="fleet.sync_pull")


class FleetSyncLogTool(Tool):
    def __init__(self, service):
        self._svc = service

    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="fleet.sync_log",
            name="Fleet Sync Log",
            description="Get the sync activity log",
            version="1.0.0",
            parameters={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Number of log entries to return"},
                },
            },
            required_permissions=["fleet.read"],
            timeout_seconds=10,
            category="fleet",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            logs = self._svc.get_sync_logs(params.get("limit", 50))
            return ToolResult.ok(data={"logs": logs}, tool_id="fleet.sync_log")
        except Exception as e:
            return ToolResult.fail(error=str(e), tool_id="fleet.sync_log")
