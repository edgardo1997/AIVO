from typing import Any, Dict, Optional

from sentinel.core.tool import Tool, ToolResult, ToolSpec
from sentinel.core import environment_snapshot as snap

_CAT = "environment"


class SnapshotCreateTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="env.snapshot.create",
            name="Create Snapshot",
            description="Capture current system state (power plan, GPU, env vars) and save as a named snapshot",
            version="1.0.0",
            category=_CAT,
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Optional name for the snapshot"},
                },
                "required": [],
            },
            required_permissions=["system.read"],
        )

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        name = params.get("name")
        snapshot = snap.create_snapshot(name)
        if not snapshot:
            return ToolResult.fail(error="Failed to create snapshot", tool_id="env.snapshot.create")
        return ToolResult.ok(data={
            "snapshot_id": snapshot.meta.id,
            "name": snapshot.meta.name,
            "created_at": snapshot.meta.created_at,
            "state_count": snapshot.meta.state_count,
        }, tool_id="env.snapshot.create")


class SnapshotListTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="env.snapshot.list",
            name="List Snapshots",
            description="List all saved system state snapshots",
            version="1.0.0",
            category=_CAT,
            parameters={"type": "object", "properties": {}, "required": []},
            required_permissions=["system.read"],
        )

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        metas = snap.list_snapshots()
        return ToolResult.ok(data={
            "snapshots": [
                {"id": m.id, "name": m.name, "created_at": m.created_at, "state_count": m.state_count}
                for m in metas
            ],
            "count": len(metas),
        }, tool_id="env.snapshot.list")


class SnapshotGetTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="env.snapshot.get",
            name="Get Snapshot",
            description="Get details of a specific snapshot by ID",
            version="1.0.0",
            category=_CAT,
            parameters={
                "type": "object",
                "properties": {
                    "snapshot_id": {"type": "string", "description": "Snapshot ID"},
                },
                "required": ["snapshot_id"],
            },
            required_permissions=["system.read"],
        )

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        snap_id = params.get("snapshot_id", "")
        if not snap_id:
            return ToolResult.fail(error="snapshot_id parameter is required", tool_id="env.snapshot.get")
        snapshot = snap.get_snapshot(snap_id)
        if not snapshot:
            return ToolResult.fail(error=f"Snapshot '{snap_id}' not found", tool_id="env.snapshot.get")
        return ToolResult.ok(data={
            "meta": {"id": snapshot.meta.id, "name": snapshot.meta.name, "created_at": snapshot.meta.created_at},
            "state": {
                "power_plan": snapshot.state.power_plan,
                "gpu_count": len(snapshot.state.gpu),
                "env_vars": snapshot.state.env_vars,
            },
        }, tool_id="env.snapshot.get")


class SnapshotRestoreTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="env.snapshot.restore",
            name="Restore Snapshot",
            description="Restore system state from a saved snapshot (power plan, GPU settings)",
            version="1.0.0",
            category=_CAT,
            parameters={
                "type": "object",
                "properties": {
                    "snapshot_id": {"type": "string", "description": "Snapshot ID to restore"},
                },
                "required": ["snapshot_id"],
            },
            required_permissions=["system.write"],
        )

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        snap_id = params.get("snapshot_id", "")
        if not snap_id:
            return ToolResult.fail(error="snapshot_id parameter is required", tool_id="env.snapshot.restore")
        result = snap.restore_snapshot(snap_id)
        if not result["success"]:
            return ToolResult.fail(error=result.get("error", "Restore failed"), tool_id="env.snapshot.restore")
        return ToolResult.ok(data=result, tool_id="env.snapshot.restore")


class SnapshotDeleteTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="env.snapshot.delete",
            name="Delete Snapshot",
            description="Delete a saved snapshot by ID",
            version="1.0.0",
            category=_CAT,
            parameters={
                "type": "object",
                "properties": {
                    "snapshot_id": {"type": "string", "description": "Snapshot ID to delete"},
                },
                "required": ["snapshot_id"],
            },
            required_permissions=["system.write"],
        )

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        snap_id = params.get("snapshot_id", "")
        if not snap_id:
            return ToolResult.fail(error="snapshot_id parameter is required", tool_id="env.snapshot.delete")
        result = snap.delete_snapshot(snap_id)
        if not result["success"]:
            return ToolResult.fail(error=result.get("error", "Delete failed"), tool_id="env.snapshot.delete")
        return ToolResult.ok(data=result, tool_id="env.snapshot.delete")
