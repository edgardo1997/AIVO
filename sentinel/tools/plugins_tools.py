from typing import Any, Dict
from sentinel.core.tool import Tool, ToolResult, ToolSpec


class PluginListTool(Tool):
    def __init__(self, service):
        self._svc = service

    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="plugins.list",
            name="List Plugins",
            description="List all registered plugins",
            version="1.0.0",
            parameters={},
            required_permissions=["plugins.read"],
            timeout_seconds=10,
            category="plugins",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            result = self._svc.list_all()
            return ToolResult.ok(data=result, tool_id="plugins.list")
        except Exception as e:
            return ToolResult.fail(error=str(e), tool_id="plugins.list")


class PluginTemplatesTool(Tool):
    def __init__(self, service):
        self._svc = service

    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="plugins.templates",
            name="Plugin Templates",
            description="List available plugin templates",
            version="1.0.0",
            parameters={},
            required_permissions=["plugins.read"],
            timeout_seconds=10,
            category="plugins",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            result = self._svc.list_templates()
            return ToolResult.ok(data=result, tool_id="plugins.templates")
        except Exception as e:
            return ToolResult.fail(error=str(e), tool_id="plugins.templates")


class PluginLoadTool(Tool):
    def __init__(self, service):
        self._svc = service

    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="plugins.load",
            name="Load Plugin",
            description="Load a plugin by ID",
            version="1.0.0",
            parameters={
                "type": "object",
                "properties": {
                    "plugin_id": {"type": "string", "description": "Plugin ID to load"},
                },
                "required": ["plugin_id"],
            },
            required_permissions=["plugins.admin"],
            timeout_seconds=30,
            category="plugins",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            result = self._svc.load(params["plugin_id"])
            if result is None:
                return ToolResult.fail(
                    error=f"Plugin '{params['plugin_id']}' not found or has no loadable code", tool_id="plugins.load"
                )
            return ToolResult.ok(data=result, tool_id="plugins.load")
        except Exception as e:
            return ToolResult.fail(error=str(e), tool_id="plugins.load")


class PluginUnloadTool(Tool):
    def __init__(self, service):
        self._svc = service

    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="plugins.unload",
            name="Unload Plugin",
            description="Unload a plugin by ID",
            version="1.0.0",
            parameters={
                "type": "object",
                "properties": {
                    "plugin_id": {"type": "string", "description": "Plugin ID to unload"},
                },
                "required": ["plugin_id"],
            },
            required_permissions=["plugins.admin"],
            timeout_seconds=10,
            category="plugins",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            self._svc.unload(params["plugin_id"])
            return ToolResult.ok(data={"status": "unloaded"}, tool_id="plugins.unload")
        except Exception as e:
            return ToolResult.fail(error=str(e), tool_id="plugins.unload")


class PluginReloadTool(Tool):
    def __init__(self, service):
        self._svc = service

    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="plugins.reload",
            name="Reload Plugin",
            description="Reload a plugin by ID",
            version="1.0.0",
            parameters={
                "type": "object",
                "properties": {
                    "plugin_id": {"type": "string", "description": "Plugin ID to reload"},
                },
                "required": ["plugin_id"],
            },
            required_permissions=["plugins.admin"],
            timeout_seconds=30,
            category="plugins",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            result = self._svc.reload(params["plugin_id"])
            return ToolResult.ok(data=result or {}, tool_id="plugins.reload")
        except Exception as e:
            return ToolResult.fail(error=str(e), tool_id="plugins.reload")


class PluginToggleTool(Tool):
    def __init__(self, service):
        self._svc = service

    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="plugins.toggle",
            name="Toggle Plugin",
            description="Enable or disable a plugin",
            version="1.0.0",
            parameters={
                "type": "object",
                "properties": {
                    "plugin_id": {"type": "string", "description": "Plugin ID to toggle"},
                },
                "required": ["plugin_id"],
            },
            required_permissions=["plugins.admin"],
            timeout_seconds=10,
            category="plugins",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            result = self._svc.toggle(params["plugin_id"])
            return ToolResult.ok(data=result, tool_id="plugins.toggle")
        except Exception as e:
            return ToolResult.fail(error=str(e), tool_id="plugins.toggle")


class PluginCreateTool(Tool):
    def __init__(self, service):
        self._svc = service

    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="plugins.create",
            name="Create Plugin",
            description="Create a new plugin from a template",
            version="1.0.0",
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Plugin name"},
                    "template": {"type": "string", "description": "Template to use"},
                },
                "required": ["name"],
            },
            required_permissions=["plugins.admin"],
            timeout_seconds=10,
            category="plugins",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            result = self._svc.create(params["name"], params.get("template", "minimal"))
            self._svc.list_all()
            return ToolResult.ok(data=result, tool_id="plugins.create")
        except Exception as e:
            return ToolResult.fail(error=str(e), tool_id="plugins.create")


class PluginInstallUrlTool(Tool):
    def __init__(self, service):
        self._svc = service

    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="plugins.install_url",
            name="Install Plugin from URL",
            description="Install a plugin from a remote URL",
            version="1.0.0",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to the plugin zip"},
                    "plugin_id": {"type": "string", "description": "Optional plugin ID override"},
                },
                "required": ["url"],
            },
            required_permissions=["plugins.admin"],
            timeout_seconds=60,
            category="plugins",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            url = params["url"]
            plugin_id = params.get("plugin_id", "")
            result = self._svc.install_from_url(url, plugin_id)
            return ToolResult.ok(data=result, tool_id="plugins.install_url")
        except Exception as e:
            return ToolResult.fail(error=str(e), tool_id="plugins.install_url")


class PluginInstallZipTool(Tool):
    def __init__(self, service):
        self._svc = service

    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="plugins.install_zip",
            name="Install Plugin from ZIP",
            description="Install a plugin from a base64-encoded zip",
            version="1.0.0",
            parameters={
                "type": "object",
                "properties": {
                    "zip_base64": {"type": "string", "description": "Base64-encoded plugin zip"},
                    "plugin_id": {"type": "string", "description": "Optional plugin ID override"},
                },
                "required": ["zip_base64"],
            },
            required_permissions=["plugins.admin"],
            timeout_seconds=30,
            category="plugins",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            import base64
            raw = base64.b64decode(params["zip_base64"])
            plugin_id = params.get("plugin_id", "")
            result = self._svc.install_from_zip(raw, plugin_id)
            return ToolResult.ok(data=result, tool_id="plugins.install_zip")
        except Exception as e:
            return ToolResult.fail(error=str(e), tool_id="plugins.install_zip")
