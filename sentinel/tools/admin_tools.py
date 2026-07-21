import json
import os
import shutil
from datetime import datetime, timezone
from typing import Any, Dict

from sentinel.core.tool import Tool, ToolResult, ToolSpec


class ConfigSetTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="admin.config_set",
            name="Set Config",
            description="Set an admin configuration value",
            version="1.0.0",
            parameters={
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Config key"},
                    "value": {"description": "Config value (string, dict, or list)"},
                },
                "required": ["key", "value"],
            },
            required_permissions=["admin.config"],
            timeout_seconds=10,
            category="admin",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            from repositories.database import DatabaseManager
            db = DatabaseManager()
            key = params["key"]
            raw = params.get("value")
            if isinstance(raw, (dict, list)):
                db.config_set_json(key, raw)
            else:
                db.config_set(key, str(raw) if raw is not None else "")
            return ToolResult.ok(data={"status": "ok", "key": key}, tool_id="admin.config_set")
        except Exception as e:
            return ToolResult.fail(error=str(e), tool_id="admin.config_set")


class ConfigDeleteTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="admin.config_delete",
            name="Delete Config",
            description="Delete an admin configuration key",
            version="1.0.0",
            parameters={
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Config key to delete"},
                },
                "required": ["key"],
            },
            required_permissions=["admin.config"],
            timeout_seconds=10,
            category="admin",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            from repositories.database import DatabaseManager
            db = DatabaseManager()
            key = params["key"]
            db.config_delete(key)
            return ToolResult.ok(data={"status": "ok", "key": key}, tool_id="admin.config_delete")
        except Exception as e:
            return ToolResult.fail(error=str(e), tool_id="admin.config_delete")


class BackupTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="admin.backup",
            name="Create Backup",
            description="Create a database backup",
            version="1.0.0",
            parameters={},
            required_permissions=["admin.backup"],
            timeout_seconds=30,
            category="admin",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            from repositories.database import DatabaseManager
            from windows_acl import sentinel_storage_paths

            db = DatabaseManager()
            src = db.db_path
            if not os.path.exists(src):
                return ToolResult.fail(error="Database file not found", tool_id="admin.backup")
            storage = sentinel_storage_paths()
            backup_dir = storage["runtime"] / "backups"
            backup_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            dest = backup_dir / f"sentinel-backup-{ts}.db"
            shutil.copy2(src, dest)
            for suffix in ("-wal", "-shm"):
                sidecar = f"{src}{suffix}"
                if os.path.exists(sidecar):
                    shutil.copy2(sidecar, f"{dest}{suffix}")
            return ToolResult.ok(
                data={"status": "ok", "path": str(dest), "size_bytes": os.path.getsize(dest)},
                tool_id="admin.backup",
            )
        except Exception as e:
            return ToolResult.fail(error=str(e), tool_id="admin.backup")
