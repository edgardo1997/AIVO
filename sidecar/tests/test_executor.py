from conftest import admin_mode, confirm_mode
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_run_safe_command():
    admin_mode()
    resp = client.post("/v1/execute", json={"tool_id": "executor.command", "params": {"command": "echo hello", "timeout": 10}})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "stdout" in data
    assert "hello" in data["stdout"]
    assert data["returncode"] == 0

def test_run_command_with_output():
    admin_mode()
    resp = client.post("/v1/execute", json={"tool_id": "executor.command", "params": {"command": "echo test_output", "timeout": 10}})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["stdout"].strip() == "test_output"
    assert data["returncode"] == 0

def test_shell_loop_is_blocked_before_timeout():
    admin_mode()
    resp = client.post("/v1/execute", json={"tool_id": "executor.command", "params": {"command": "for /l %i in () do echo.", "timeout": 1}})
    body = resp.json()
    assert body["success"] is False
    assert body["data"] is None
    assert "shell chaining" in body["error"].lower()

def test_run_destructive_command_requires_confirm():
    confirm_mode()
    resp = client.post("/v1/execute", json={"tool_id": "executor.command", "params": {"command": "format X:", "timeout": 10}})
    assert resp.status_code == 200
    assert resp.json()["requires_confirmation"] == True

def test_classify_command_safe():
    from modules.executor import _svc
    assert _svc.classify_command("dir") == "safe"
    assert _svc.classify_command("echo test") == "safe"
    assert _svc.classify_command("dir /w") == "safe"

def test_classify_command_destructive():
    from modules.executor import _svc
    assert "DESTRUCTIVE" in _svc.classify_command("rm -rf /")
    assert "DESTRUCTIVE" in _svc.classify_command("del /f file.txt")
    assert "DESTRUCTIVE" in _svc.classify_command("format C:")

def test_classify_command_unknown():
    from modules.executor import _svc
    assert _svc.classify_command("my_custom_tool --help") == "unknown"

def test_destructive_patterns_endpoint():
    from modules.executor import _svc
    patterns = _svc.get_destructive_patterns()
    assert "patterns" in patterns
    assert len(patterns["patterns"]) > 0
