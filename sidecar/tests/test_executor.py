from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_run_safe_command():
    resp = client.post("/api/executor/command", json={
        "command": "echo hello",
        "timeout": 10,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "stdout" in data
    assert "hello" in data["stdout"]
    assert data["returncode"] == 0

def test_run_command_with_output():
    resp = client.post("/api/executor/command", json={
        "command": "echo test_output",
        "timeout": 10,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["stdout"].strip() == "test_output"
    assert data["returncode"] == 0

def test_run_command_timeout():
    resp = client.post("/api/executor/command", json={
        "command": "ping -n 60 127.0.0.1",
        "timeout": 1,
    })
    data = resp.json()
    assert data["returncode"] == -1
    assert "timed out" in data["stderr"].lower()

def test_run_destructive_command_requires_confirm():
    resp = client.post("/api/executor/command", json={
        "command": "format X:",
        "timeout": 10,
    })
    data = resp.json()
    assert data.get("needs_confirm", False)

def test_classify_command_safe():
    from modules.executor import classify_command
    assert classify_command("dir") == "safe"
    assert classify_command("echo test") == "safe"
    assert classify_command("dir /w") == "safe"

def test_classify_command_destructive():
    from modules.executor import classify_command
    assert "DESTRUCTIVE" in classify_command("rm -rf /")
    assert "DESTRUCTIVE" in classify_command("del /f file.txt")
    assert "DESTRUCTIVE" in classify_command("format C:")

def test_classify_command_unknown():
    from modules.executor import classify_command
    assert classify_command("my_custom_tool --help") == "unknown"

def test_list_apps():
    resp = client.get("/api/executor/apps")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) > 0
    assert "cmd" in data or "powershell" in data or "python" in data

def test_destructive_patterns_endpoint():
    resp = client.get("/api/executor/destructive-patterns")
    assert resp.status_code == 200
    data = resp.json()
    assert "patterns" in data
    assert len(data["patterns"]) > 0
