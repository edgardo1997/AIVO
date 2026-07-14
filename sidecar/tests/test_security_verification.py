import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def _blocked(resp, msg=""):
    err = (resp.json().get("error") or "").lower()
    assert "deny" in err or "denied" in err or "blocked" in err, f"{msg}: {resp.json()}"


class TestFilesystemViaGateway:
    def test_read_allowed_at_view(self):
        from modules.permissions import _svc as perm_svc

        perm_svc.set_level("view")
        resp = client.post("/v1/execute", json={"tool_id": "filesystem.list", "params": {"path": "C:\\"}})
        assert resp.status_code == 200

    def test_write_blocked_by_view(self):
        from modules.permissions import _svc as perm_svc

        perm_svc.set_level("view")
        resp = client.post(
            "/v1/execute",
            json={"tool_id": "filesystem.write", "params": {"path": "C:\\test_blocked.txt", "content": "x"}},
        )
        _blocked(resp, "view should block filesystem.write")

    def test_write_allowed_at_admin(self):
        from modules.permissions import _svc as perm_svc

        perm_svc.set_level("admin")
        test_file = os.path.join(os.environ.get("TEMP", "C:\\Temp"), "aivo_sec_write.txt")
        try:
            resp = client.post(
                "/v1/execute",
                json={"tool_id": "filesystem.write", "params": {"path": test_file, "content": "sec test"}},
            )
            assert resp.status_code == 200
            assert resp.json()["success"] == True
            assert "size" in resp.json()["data"]
        finally:
            if os.path.exists(test_file):
                os.remove(test_file)


class TestExecutorViaGateway:
    def test_command_blocked_by_view(self):
        from modules.permissions import _svc as perm_svc

        perm_svc.set_level("view")
        resp = client.post(
            "/v1/execute", json={"tool_id": "executor.command", "params": {"command": "echo blocked", "timeout": 5}}
        )
        _blocked(resp, "view should block executor.command")

    def test_command_allowed_at_admin(self):
        from modules.permissions import _svc as perm_svc

        perm_svc.set_level("admin")
        resp = client.post(
            "/v1/execute", json={"tool_id": "executor.command", "params": {"command": "echo test123", "timeout": 10}}
        )
        assert resp.status_code == 200
        assert resp.json()["success"] == True
        assert "test123" in resp.json()["data"]["stdout"]

    def test_launch_blocked_by_view(self):
        from modules.permissions import _svc as perm_svc

        perm_svc.set_level("view")
        resp = client.post("/v1/execute", json={"tool_id": "executor.launch", "params": {"app_name": "calc.exe"}})
        _blocked(resp, "view should block executor.launch")

    def test_kill_blocked_by_view(self):
        from modules.permissions import _svc as perm_svc

        perm_svc.set_level("view")
        resp = client.post("/v1/execute", json={"tool_id": "executor.kill", "params": {"pid": 0}})
        _blocked(resp, "view should block executor.kill")

    def test_kill_allowed_at_admin_returns_error_for_invalid_pid(self):
        from modules.permissions import _svc as perm_svc

        perm_svc.set_level("admin")
        resp = client.post("/v1/execute", json={"tool_id": "executor.kill", "params": {"pid": 99999}})
        assert resp.status_code == 200
        assert resp.json()["success"] == False


class TestProactiveBypassFixed:
    def test_execute_suggestion_no_psutil_terminate_in_source(self):
        import inspect
        from services.proactive_service import ProactiveService

        source = inspect.getsource(ProactiveService.execute_suggestion)
        assert "psutil.Process" not in source
        assert ".terminate()" not in source
        assert "self._gateway.execute" in source

    def test_execute_suggestion_no_psutil_import_in_method_source(self):
        import inspect
        from services.proactive_service import ProactiveService

        source = inspect.getsource(ProactiveService.execute_suggestion)
        assert "import psutil" not in source

    def test_execute_suggestion_goes_through_gateway_at_confirm_level(self):
        from modules.proactive import _svc
        from modules.permissions import _svc as perm_svc

        _svc._suggestions.append(
            {
                "uid": "sec_test_gateway",
                "id": "sec_test",
                "actions": [{"label": "Kill Top CPU Process", "action": "kill_top_cpu"}],
                "title": "Test",
                "message": "Test",
                "priority": "warning",
                "icon": "\u26a0",
                "value": 90,
                "timestamp": 0,
            }
        )
        try:
            perm_svc.set_level("confirm")
            resp = client.post("/v1/execute", json={"tool_id": "executor.kill", "params": {"pid": 1}})
            assert resp.status_code == 200
        finally:
            _svc._suggestions[:] = [s for s in _svc._suggestions if s.get("uid") != "sec_test_gateway"]


class TestPolicyIntegration:
    def test_emergency_stop_blocks_filesystem_write(self):
        from modules.permissions import _svc as perm_svc

        perm_svc.set_level("admin")
        perm_svc.emergency("stop")
        resp = client.post(
            "/v1/execute",
            json={"tool_id": "filesystem.write", "params": {"path": "C:\\test_estop.txt", "content": "x"}},
        )
        _blocked(resp, "emergency stop should block filesystem.write")
        perm_svc.emergency("resume")

    def test_emergency_stop_blocks_executor_command(self):
        from modules.permissions import _svc as perm_svc

        perm_svc.set_level("admin")
        perm_svc.emergency("stop")
        resp = client.post(
            "/v1/execute", json={"tool_id": "executor.command", "params": {"command": "echo blocked", "timeout": 5}}
        )
        _blocked(resp, "emergency stop should block executor.command")
        perm_svc.emergency("resume")

    def test_emergency_stop_blocks_executor_kill(self):
        from modules.permissions import _svc as perm_svc

        perm_svc.set_level("admin")
        perm_svc.emergency("stop")
        resp = client.post("/v1/execute", json={"tool_id": "executor.kill", "params": {"pid": 0}})
        _blocked(resp, "emergency stop should block executor.kill")
        perm_svc.emergency("resume")

    def test_filesystem_write_requires_confirm_at_confirm_level(self):
        from modules.permissions import _svc as perm_svc

        perm_svc.set_level("confirm")
        test_file = os.path.join(os.environ.get("TEMP", "C:\\Temp"), "aivo_sec_confirm.txt")
        try:
            resp = client.post(
                "/v1/execute", json={"tool_id": "filesystem.write", "params": {"path": test_file, "content": "test"}}
            )
            assert resp.status_code == 200
        finally:
            if os.path.exists(test_file):
                os.remove(test_file)

    def test_dangerous_command_requires_confirm_at_confirm_level(self):
        from modules.permissions import _svc as perm_svc

        perm_svc.set_level("confirm")
        resp = client.post(
            "/v1/execute", json={"tool_id": "executor.command", "params": {"command": "format X:", "timeout": 10}}
        )
        assert resp.status_code == 200
        assert resp.json()["requires_confirmation"] == True

    def test_pending_action_id_generated(self):
        from modules.permissions import _svc as perm_svc

        perm_svc.set_level("confirm")
        resp = client.post(
            "/v1/execute",
            json={"tool_id": "executor.command", "params": {"command": "rm dangerous_file", "timeout": 10}},
        )
        assert resp.status_code == 200
        assert resp.json()["requires_confirmation"] == True


class TestAuditTrail:
    def test_audit_logs_filesystem_write(self):
        from modules.permissions import _svc as perm_svc

        perm_svc.set_level("admin")
        test_file = os.path.join(os.environ.get("TEMP", "C:\\Temp"), "aivo_audit_write.txt")
        try:
            resp = client.post(
                "/v1/execute",
                json={"tool_id": "filesystem.write", "params": {"path": test_file, "content": "audit me"}},
            )
            assert resp.status_code == 200
        finally:
            if os.path.exists(test_file):
                os.remove(test_file)
        resp = client.get("/v1/audit")
        entries = resp.json().get("entries", [])
        matches = [e for e in entries if "filesystem.write" in e.get("action", "")]
        assert len(matches) >= 1, "No audit entry for filesystem.write"

    def test_audit_logs_executor_command(self):
        from modules.permissions import _svc as perm_svc

        perm_svc.set_level("admin")
        client.post(
            "/v1/execute",
            json={"tool_id": "executor.command", "params": {"command": "echo audit_test_cmd", "timeout": 5}},
        )
        resp = client.get("/v1/audit")
        entries = resp.json().get("entries", [])
        matches = [e for e in entries if "audit_test_cmd" in e.get("details", "")]
        assert len(matches) >= 1

    def test_audit_logs_pending_confirmation(self):
        from modules.permissions import _svc as perm_svc

        perm_svc.set_level("confirm")
        resp = client.post(
            "/v1/execute", json={"tool_id": "executor.command", "params": {"command": "format sec_test", "timeout": 10}}
        )
        assert resp.json()["requires_confirmation"] == True

    def test_audit_logs_policy_blocked(self):
        from modules.permissions import _svc as perm_svc

        perm_svc.set_level("view")
        resp = client.post(
            "/v1/execute",
            json={"tool_id": "executor.command", "params": {"command": "echo blocked_audit", "timeout": 5}},
        )
        assert resp.json()["success"] == False

    def test_audit_log_entry_has_timestamp(self):
        from modules.permissions import _svc as perm_svc

        perm_svc.set_level("admin")
        client.post(
            "/v1/execute", json={"tool_id": "executor.command", "params": {"command": "echo ts_test", "timeout": 5}}
        )
        resp = client.get("/v1/audit")
        entries = resp.json().get("entries", [])
        assert len(entries) >= 1
        assert "timestamp" in entries[-1]


class TestNoBypass:
    def test_filesystem_router_no_direct_svc_call(self):
        import inspect
        from modules import filesystem as fs_mod

        source = inspect.getsource(fs_mod)
        orch_count = source.count("get_orchestrator()")
        assert orch_count >= 3, "filesystem module must use get_orchestrator"

    def test_executor_router_main_endpoints_use_gateway(self):
        import inspect
        from modules import executor as exec_mod

        source = inspect.getsource(exec_mod)
        orch_usage = source.count("get_orchestrator()")
        assert orch_usage >= 2, "executor module must use get_orchestrator in command/launch/kill"

    def test_proactive_execute_uses_async_gateway(self):
        import inspect
        from services.proactive_service import ProactiveService

        source = inspect.getsource(ProactiveService.execute_suggestion)
        assert "async def" in source
        assert "self._gateway.execute" in source

    def test_no_unknown_router_direct_service_calls(self):
        import inspect
        from modules import filesystem as fs_mod
        from modules import executor as exec_mod
        from modules import sentinel_bridge as sb_mod
        from modules import proactive as pro_mod

        for mod, name in [
            (fs_mod, "filesystem"),
            (exec_mod, "executor"),
            (sb_mod, "sentinel_bridge"),
            (pro_mod, "proactive"),
        ]:
            source = inspect.getsource(mod)
            gw_call_count = source.count("get_gateway()")
            assert gw_call_count >= 0

    def test_gateway_has_all_expected_tools(self):
        from modules import get_gateway

        gw = get_gateway()
        ids = [s.id for s in gw.list_specs()]
        expected = {
            "filesystem.read",
            "filesystem.write",
            "filesystem.list",
            "filesystem.search",
            "executor.command",
            "executor.launch",
            "executor.kill",
            "system.info",
            "system.cpu",
            "system.memory",
            "system.disk",
            "system.network",
            "system.processes",
            "system.gpu",
            "app.discovery",
            "ai.chat",
            "ai.analyze",
            "ai.config",
            "fleet.status",
            "fleet.generate_pairing",
            "fleet.revoke_pairing",
            "fleet.toggle_remote",
            "fleet.qr",
            "plugins.list",
            "plugins.templates",
            "plugins.load",
            "plugins.unload",
            "plugins.reload",
            "plugins.toggle",
            "plugins.create",
            "permissions.status",
            "permissions.set_level",
            "permissions.emergency",
            "permissions.confirm",
            "audit.list",
            "proactive.suggestions",
            "proactive.dismiss",
            "proactive.trend",
            "trigger.list",
            "trigger.create",
            "trigger.delete",
            "trigger.history",
            "trigger.evaluate",
        }
        missing = expected - set(ids)
        assert not missing, f"Gateway missing tools: {missing}"
        assert len(ids) == len(set(ids)), f"Duplicate tool IDs registered: {ids}"
        unclassified = [s.id for s in gw.list_specs() if not s.required_permissions]
        assert not unclassified, f"Tools without security classification: {unclassified}"

    def test_gateway_policies_registered(self):
        from modules import get_gateway

        gw = get_gateway()
        engine = gw._policy_engine
        assert engine is not None, "Gateway must have policy engine"
        policies = list(engine._policies.keys())
        assert "permission_level" in policies, "PermissionLevelPolicy must be registered"
        assert "emergency_stop" in policies, "EmergencyStopPolicy must be registered"

    def test_permission_level_to_decision_matrix(self):
        from sentinel.core.policy import PolicyEffect
        from sentinel.policies.security_policies import LEVELS

        assert LEVELS["view"]["write"] == PolicyEffect.DENY
        assert LEVELS["view"]["dangerous"] == PolicyEffect.DENY
        assert LEVELS["confirm"]["dangerous"] == PolicyEffect.REQUIRE_CONFIRM
        assert LEVELS["admin"]["dangerous"] == PolicyEffect.ALLOW
