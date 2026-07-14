from typing import Any, Dict, Optional

from sentinel.core.integrations import DesktopIntegrationService
from sentinel.core.tool import Tool, ToolResult, ToolSpec


class _IntegrationTool(Tool):
    tool_id = ""
    tool_name = ""
    description = ""
    permissions = ["system.read"]
    parameters: Dict[str, Any] = {"type": "object", "properties": {}}

    def __init__(self, service: DesktopIntegrationService):
        self._service = service

    def spec(self) -> ToolSpec:
        return ToolSpec(
            id=self.tool_id,
            name=self.tool_name,
            description=self.description,
            version="1.0.0",
            category="integration",
            parameters=self.parameters,
            required_permissions=self.permissions,
        )


class IntegrationStatusTool(_IntegrationTool):
    tool_id = "integration.status"
    tool_name = "Integration Status"
    description = "Detect real IDE, browser, document, image and operating-system adapters."

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        return ToolResult.ok(self._service.status(), self.tool_id)


class IdeOpenTool(_IntegrationTool):
    tool_id = "ide.open"
    tool_name = "Open in IDE"
    description = "Open an existing file or workspace in VS Code, Code Insiders or VSCodium."
    permissions = ["filesystem.read", "executor.launch"]
    parameters = {
        "type": "object",
        "properties": {"path": {"type": "string"}, "line": {"type": "integer", "minimum": 1}},
        "required": ["path"],
    }

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        try:
            return ToolResult.ok(self._service.open_ide(params.get("path", ""), params.get("line")), self.tool_id)
        except Exception as exc:
            return ToolResult.fail(str(exc), self.tool_id)


class BrowserOpenTool(_IntegrationTool):
    tool_id = "browser.open"
    tool_name = "Open Browser"
    description = "Open a validated HTTP or HTTPS URL in the default desktop browser."
    permissions = ["executor.launch"]
    parameters = {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        try:
            return ToolResult.ok(self._service.open_browser(params.get("url", "")), self.tool_id)
        except Exception as exc:
            return ToolResult.fail(str(exc), self.tool_id)


class FileOpenTool(_IntegrationTool):
    integration = "document"
    permissions = ["filesystem.read", "executor.launch"]
    parameters = {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        try:
            return ToolResult.ok(self._service.open_file(params.get("path", ""), self.integration), self.tool_id)
        except Exception as exc:
            return ToolResult.fail(str(exc), self.tool_id)


class DocumentOpenTool(FileOpenTool):
    tool_id = "document.open"
    tool_name = "Open Document"
    description = "Open an existing document with its operating-system application."


class ImageOpenTool(FileOpenTool):
    tool_id = "image.open"
    tool_name = "Open Image"
    description = "Open an existing image with the operating-system viewer."
    integration = "image"


class ImageInspectTool(_IntegrationTool):
    tool_id = "image.inspect"
    tool_name = "Inspect Image"
    description = "Read real image metadata and dimensions without launching an application."
    permissions = ["filesystem.read"]
    parameters = {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        try:
            return ToolResult.ok(self._service.inspect_image(params.get("path", "")), self.tool_id)
        except Exception as exc:
            return ToolResult.fail(str(exc), self.tool_id)


class OsRevealTool(_IntegrationTool):
    tool_id = "os.reveal"
    tool_name = "Reveal in Operating System"
    description = "Reveal an existing path in Explorer, Finder or the platform file manager."
    permissions = ["filesystem.read", "executor.launch"]
    parameters = {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        try:
            return ToolResult.ok(self._service.reveal_path(params.get("path", "")), self.tool_id)
        except Exception as exc:
            return ToolResult.fail(str(exc), self.tool_id)
