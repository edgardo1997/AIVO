import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


class TestToolRegistration:
    def test_active_tool_without_permissions_is_rejected(self):
        from sentinel.core.tool import Tool, ToolResult, ToolSpec
        from sentinel.core.tool_gateway import ToolGateway

        class UnclassifiedTool(Tool):
            def spec(self):
                return ToolSpec(
                    id="test.unclassified", name="Unclassified",
                    description="Must never become executable", version="1.0.0",
                    parameters={}, required_permissions=[],
                )

            async def execute(self, params, context):
                return ToolResult.ok({})

        with pytest.raises(ValueError, match="must declare at least one required permission"):
            ToolGateway().register(UnclassifiedTool())

    def test_gateway_initialized(self):
        from modules import get_gateway
        gw = get_gateway()
        assert gw is not None
        specs = gw.list_specs()
        assert len(specs) > 0

    def test_filesystem_tools_registered(self):
        from modules import get_gateway
        gw = get_gateway()
        ids = [s.id for s in gw.list_specs()]
        for tid in ["filesystem.read", "filesystem.write", "filesystem.list", "filesystem.search"]:
            assert tid in ids, f"Tool {tid} not registered"

    def test_executor_tools_registered(self):
        from modules import get_gateway
        gw = get_gateway()
        ids = [s.id for s in gw.list_specs()]
        for tid in ["executor.command", "executor.launch", "executor.kill"]:
            assert tid in ids, f"Tool {tid} not registered"

    def test_sentinel_tools_still_registered(self):
        from modules import get_gateway
        gw = get_gateway()
        ids = [s.id for s in gw.list_specs()]
        for tid in ["system.info", "system.cpu", "system.processes"]:
            assert tid in ids, f"Tool {tid} not registered"


class TestFilesystemTools:
    def test_read_tool_spec(self):
        from services.filesystem_service import FilesystemService
        tool = FilesystemService(tool_id="filesystem.read")
        spec = tool.spec()
        assert spec.id == "filesystem.read"
        assert "filesystem.read" in spec.required_permissions
        assert "path" in spec.parameters.get("properties", {})

    def test_write_tool_spec(self):
        from services.filesystem_service import FilesystemService
        tool = FilesystemService(tool_id="filesystem.write")
        spec = tool.spec()
        assert spec.id == "filesystem.write"
        assert "content" in spec.parameters.get("properties", {})

    def test_list_tool_spec(self):
        from services.filesystem_service import FilesystemService
        tool = FilesystemService(tool_id="filesystem.list")
        spec = tool.spec()
        assert spec.id == "filesystem.list"

    def test_via_gateway_read_allowed(self):
        tmp = tempfile.gettempdir()
        test_file = os.path.join(tmp, "aivo_tool_test.txt")
        try:
            with open(test_file, "w") as f:
                f.write("tool test")
            resp = client.post("/v1/execute", json={"tool_id": "filesystem.read", "params": {"path": test_file}})
            assert resp.status_code == 200
            assert resp.json()["success"] == True
            assert "content" in resp.json()["data"]
        finally:
            if os.path.exists(test_file):
                os.remove(test_file)


class TestExecutorTools:
    def test_command_tool_spec(self):
        from services.executor_service import ExecutorService
        tool = ExecutorService()
        spec = tool.spec()
        assert spec.id == "executor.command"
        assert "command" in spec.parameters.get("properties", {})

    def test_launch_tool_spec(self):
        from services.executor_service import ExecutorService
        tool = ExecutorService()
        spec = tool.spec_launch()
        assert spec.id == "executor.launch"

    def test_kill_tool_spec(self):
        from services.executor_service import ExecutorService
        tool = ExecutorService()
        spec = tool.spec_kill()
        assert spec.id == "executor.kill"

    def test_executor_endpoint_still_works(self):
        from modules.permissions import _svc as perm_svc
        perm_svc.set_level("admin")
        resp = client.post("/v1/execute", json={"tool_id": "executor.command", "params": {"command": "echo hello", "timeout": 10}})
        assert resp.status_code == 200
        assert resp.json()["success"] == True
        assert "stdout" in resp.json()["data"]

    def test_executor_del_in_temp_allowed(self):
        from modules.permissions import _svc as perm_svc
        tmp = tempfile.gettempdir()
        test_file = os.path.join(tmp, "aivo_tool_del_test.txt")
        try:
            with open(test_file, "w") as f:
                f.write("delete me")
            perm_svc.set_level("admin")
            resp = client.post("/v1/execute", json={"tool_id": "executor.command", "params": {"command": f"del \"{test_file}\"", "timeout": 10}})
            assert resp.status_code == 200
        finally:
            if os.path.exists(test_file):
                os.remove(test_file)


class TestDelegation:
    """Verify routers delegate through ToolGateway — policy changes affect HTTP behavior."""

    def test_filesystem_write_blocked_by_view_level(self):
        from modules.permissions import _svc as perm_svc
        perm_svc.set_level("view")
        tmp = tempfile.gettempdir()
        test_file = os.path.join(tmp, "aivo_deleg_write.txt")
        try:
            resp = client.post("/v1/execute", json={"tool_id": "filesystem.write", "params": {"path": test_file, "content": "test"}})
            assert resp.json()["success"] == False, "View level should block write"
        finally:
            if os.path.exists(test_file):
                os.remove(test_file)
        perm_svc.set_level("confirm")

    def test_filesystem_write_allowed_at_admin(self):
        from modules.permissions import _svc as perm_svc
        perm_svc.set_level("admin")
        tmp = tempfile.gettempdir()
        test_file = os.path.join(tmp, "aivo_deleg_admin.txt")
        try:
            resp = client.post("/v1/execute", json={"tool_id": "filesystem.write", "params": {"path": test_file, "content": "admin test"}})
            assert resp.status_code == 200, "Admin level should allow write"
        finally:
            if os.path.exists(test_file):
                os.remove(test_file)
        perm_svc.set_level("confirm")

    def test_executor_blocked_by_emergency_stop(self):
        from modules.permissions import _svc as perm_svc
        perm_svc.emergency("stop")
        resp = client.post("/v1/execute", json={"tool_id": "executor.command", "params": {"command": "echo hello", "timeout": 10}})
        assert resp.json()["success"] == False, "Emergency stop should block"
        perm_svc.emergency("resume")

    def test_executor_system_path_denied_by_guardian(self):
        from modules.permissions import _svc as perm_svc
        perm_svc.set_level("admin")
        resp = client.post("/v1/execute", json={"tool_id": "executor.command", "params": {"command": "del C:\\Windows\\System32\\drivers\\etc\\hosts", "timeout": 10}})
        assert resp.json()["success"] == False, "PathGuardian should block system path"
        perm_svc.set_level("confirm")


class TestSentinelBridge:
    def test_sentinel_capabilities_includes_all_tools(self):
        resp = client.get("/api/sentinel/capabilities")
        assert resp.status_code == 200
        data = resp.json()
        tool_ids = [t["id"] for t in data.get("tools", [])]
        for tid in ["filesystem.read", "filesystem.write", "executor.command", "system.info"]:
            assert tid in tool_ids, f"Shared gateway tool {tid} missing from sentinel capabilities"

    def test_sentinel_process_works(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "show me cpu usage"})
        assert resp.status_code == 200
        data = resp.json()
        assert "intent" in data
        assert "plan" in data
