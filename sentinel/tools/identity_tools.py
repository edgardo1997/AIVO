from typing import Any, Dict, Optional

from sentinel.core.tool import Tool, ToolResult, ToolSpec
from sentinel.core.identity import (
    get_windows_identity, identity_to_dict,
    verify_with_hello, get_credential_manager,
)

_CAT = "identity"


class IdentityWhoamiTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="identity.whoami",
            name="Windows Identity",
            description="Get current Windows user identity, admin status, elevation, session",
            version="1.0.0",
            category=_CAT,
            parameters={"type": "object", "properties": {}, "required": []},
            required_permissions=["system.read"],
        )

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        ident = get_windows_identity()
        return ToolResult.ok(data=identity_to_dict(ident), tool_id="identity.whoami")


class IdentityVerifyTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="identity.verify",
            name="Verify Identity",
            description="Verify identity via Windows Hello (biometric/PIN) for sensitive operations",
            version="1.0.0",
            category=_CAT,
            parameters={
                "type": "object",
                "properties": {
                    "purpose": {"type": "string", "description": "Reason for verification"},
                },
                "required": [],
            },
            required_permissions=["system.write"],
        )

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        purpose = params.get("purpose", "")
        result = verify_with_hello(purpose)
        if not result.success:
            return ToolResult.fail(error=result.error or "Verification failed", tool_id="identity.verify")
        return ToolResult.ok(data={"method": result.method, "verified": True}, tool_id="identity.verify")


class CredentialSetTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="identity.credential.set",
            name="Save Credential",
            description="Save a credential securely via Windows Credential Manager",
            version="1.0.0",
            category=_CAT,
            parameters={
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Credential name"},
                    "value": {"type": "string", "description": "Credential value (e.g., API key, token)"},
                },
                "required": ["key", "value"],
            },
            required_permissions=["system.write"],
        )

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        key = params.get("key", "")
        value = params.get("value", "")
        if not key:
            return ToolResult.fail(error="key parameter is required", tool_id="identity.credential.set")
        if not value:
            return ToolResult.fail(error="value parameter is required", tool_id="identity.credential.set")
        result = get_credential_manager().set(key, value)
        if not result["success"]:
            return ToolResult.fail(error=result.get("error", "Failed to save credential"), tool_id="identity.credential.set")
        return ToolResult.ok(data={"key": key, "message": result["message"]}, tool_id="identity.credential.set")


class CredentialGetTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="identity.credential.get",
            name="Get Credential",
            description="Check if a credential exists in Windows Credential Manager",
            version="1.0.0",
            category=_CAT,
            parameters={
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Credential name"},
                },
                "required": ["key"],
            },
            required_permissions=["system.read"],
        )

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        key = params.get("key", "")
        if not key:
            return ToolResult.fail(error="key parameter is required", tool_id="identity.credential.get")
        result = get_credential_manager().get(key)
        if not result["success"]:
            return ToolResult.ok(data={"key": key, "exists": False, "message": result.get("error", "")}, tool_id="identity.credential.get")
        return ToolResult.ok(data={"key": key, "exists": True}, tool_id="identity.credential.get")


class CredentialDeleteTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="identity.credential.delete",
            name="Delete Credential",
            description="Delete a credential from Windows Credential Manager",
            version="1.0.0",
            category=_CAT,
            parameters={
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Credential name"},
                },
                "required": ["key"],
            },
            required_permissions=["system.write"],
        )

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        key = params.get("key", "")
        if not key:
            return ToolResult.fail(error="key parameter is required", tool_id="identity.credential.delete")
        result = get_credential_manager().delete(key)
        if not result["success"]:
            return ToolResult.fail(error=result.get("error", "Failed to delete credential"), tool_id="identity.credential.delete")
        return ToolResult.ok(data={"key": key, "message": result["message"]}, tool_id="identity.credential.delete")


class CredentialListTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="identity.credential.list",
            name="List Credentials",
            description="List all saved Sentinel credentials in Windows Credential Manager",
            version="1.0.0",
            category=_CAT,
            parameters={"type": "object", "properties": {}, "required": []},
            required_permissions=["system.read"],
        )

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        result = get_credential_manager().list_keys()
        return ToolResult.ok(data={"keys": result.get("keys", []), "count": len(result.get("keys", []))}, tool_id="identity.credential.list")
