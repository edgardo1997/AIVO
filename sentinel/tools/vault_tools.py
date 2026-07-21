from typing import Any, Dict
from sentinel.core.tool import Tool, ToolResult, ToolSpec


def _get_vault():
    from modules import get_sentinel_vault
    return get_sentinel_vault()


class VaultCreateTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="vault.create",
            name="Create Vault Entry",
            description="Create a new vault entry",
            version="1.0.0",
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Entry name"},
                    "value": {"type": "string", "description": "Secret value"},
                    "category": {"type": "string", "description": "Category (default: general)"},
                    "masked": {"type": "boolean", "description": "Mask value in list views"},
                    "rotatable": {"type": "boolean", "description": "Allow auto-rotation"},
                    "rotation_days": {"type": "integer", "description": "Rotation interval in days"},
                    "notes": {"type": "string", "description": "Optional notes"},
                },
                "required": ["name", "value"],
            },
            required_permissions=["vault.write"],
            timeout_seconds=10,
            category="vault",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            from sentinel.core.vault import VaultEntry
            vault = _get_vault()
            if vault is None:
                return ToolResult.fail(error="Vault not available", tool_id="vault.create")
            entry = VaultEntry.from_dict(params)
            result = vault.create_entry(entry)
            if not result:
                return ToolResult.fail(error="Create failed", tool_id="vault.create")
            return ToolResult.ok(data={"status": "created", "id": result}, tool_id="vault.create")
        except Exception as e:
            return ToolResult.fail(error=str(e), tool_id="vault.create")


class VaultUpdateTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="vault.update",
            name="Update Vault Entry",
            description="Update an existing vault entry",
            version="1.0.0",
            parameters={
                "type": "object",
                "properties": {
                    "vault_id": {"type": "string", "description": "Entry ID"},
                    "name": {"type": "string", "description": "Entry name"},
                    "value": {"type": "string", "description": "Secret value"},
                    "category": {"type": "string", "description": "Category"},
                    "masked": {"type": "boolean", "description": "Mask value"},
                    "rotatable": {"type": "boolean", "description": "Allow rotation"},
                    "notes": {"type": "string", "description": "Optional notes"},
                },
                "required": ["vault_id"],
            },
            required_permissions=["vault.write"],
            timeout_seconds=10,
            category="vault",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            vault = _get_vault()
            if vault is None:
                return ToolResult.fail(error="Vault not available", tool_id="vault.update")
            vault_id = params.pop("vault_id")
            ok = vault.update_entry(vault_id, **params)
            if not ok:
                return ToolResult.fail(error="Not found", tool_id="vault.update")
            return ToolResult.ok(data={"status": "updated"}, tool_id="vault.update")
        except Exception as e:
            return ToolResult.fail(error=str(e), tool_id="vault.update")


class VaultDeleteTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="vault.delete",
            name="Delete Vault Entry",
            description="Delete a vault entry",
            version="1.0.0",
            parameters={
                "type": "object",
                "properties": {
                    "vault_id": {"type": "string", "description": "Entry ID to delete"},
                },
                "required": ["vault_id"],
            },
            required_permissions=["vault.write"],
            timeout_seconds=10,
            category="vault",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            vault = _get_vault()
            if vault is None:
                return ToolResult.fail(error="Vault not available", tool_id="vault.delete")
            ok = vault.delete_entry(params["vault_id"])
            if not ok:
                return ToolResult.fail(error="Not found", tool_id="vault.delete")
            return ToolResult.ok(data={"status": "deleted"}, tool_id="vault.delete")
        except Exception as e:
            return ToolResult.fail(error=str(e), tool_id="vault.delete")


class VaultRevealTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="vault.reveal",
            name="Reveal Vault Secret",
            description="Reveal the actual secret value of a vault entry",
            version="1.0.0",
            parameters={
                "type": "object",
                "properties": {
                    "vault_id": {"type": "string", "description": "Entry ID to reveal"},
                },
                "required": ["vault_id"],
            },
            required_permissions=["vault.write"],
            timeout_seconds=10,
            category="vault",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            vault = _get_vault()
            if vault is None:
                return ToolResult.fail(error="Vault not available", tool_id="vault.reveal")
            value = vault.reveal_value(params["vault_id"])
            if value is None:
                return ToolResult.fail(error="Not found", tool_id="vault.reveal")
            return ToolResult.ok(data={"value": value}, tool_id="vault.reveal")
        except Exception as e:
            return ToolResult.fail(error=str(e), tool_id="vault.reveal")


class VaultRotateSecretTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="vault.rotate_secret",
            name="Rotate Vault Secret",
            description="Rotate a vault entry's secret (generate new random value)",
            version="1.0.0",
            parameters={
                "type": "object",
                "properties": {
                    "vault_id": {"type": "string", "description": "Entry ID to rotate"},
                },
                "required": ["vault_id"],
            },
            required_permissions=["vault.write"],
            timeout_seconds=10,
            category="vault",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            vault = _get_vault()
            if vault is None:
                return ToolResult.fail(error="Vault not available", tool_id="vault.rotate_secret")
            ok = vault.rotate_secret(params["vault_id"])
            if not ok:
                return ToolResult.fail(error="Not found or no value", tool_id="vault.rotate_secret")
            return ToolResult.ok(data={"status": "rotated"}, tool_id="vault.rotate_secret")
        except Exception as e:
            return ToolResult.fail(error=str(e), tool_id="vault.rotate_secret")


class VaultRotateMasterKeyTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="vault.rotate_master_key",
            name="Rotate Master Key",
            description="Re-encrypt all vault entries with a new master key",
            version="1.0.0",
            parameters={},
            required_permissions=["vault.write"],
            timeout_seconds=30,
            category="vault",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            vault = _get_vault()
            if vault is None:
                return ToolResult.fail(error="Vault not available", tool_id="vault.rotate_master_key")
            ok = vault.rotate_master_key()
            if not ok:
                return ToolResult.fail(error="Cryptography not available", tool_id="vault.rotate_master_key")
            return ToolResult.ok(data={"status": "master_key_rotated"}, tool_id="vault.rotate_master_key")
        except Exception as e:
            return ToolResult.fail(error=str(e), tool_id="vault.rotate_master_key")
