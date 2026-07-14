from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_system_info():
    resp = client.post("/v1/execute", json={"tool_id": "system.info", "params": {}})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "cpu" in data
    assert "memory" in data
    assert "disk" in data
    assert "uptime_seconds" in data

def test_cpu_info():
    resp = client.post("/v1/execute", json={"tool_id": "system.cpu", "params": {}})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "overall" in data
    assert "count" in data
    assert "per_core" in data
    assert data["count"] >= 1

def test_memory_info():
    resp = client.post("/v1/execute", json={"tool_id": "system.memory", "params": {}})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "percent" in data
    assert "total" in data
    assert "used" in data
    assert 0 <= data["percent"] <= 100
    assert data["total"] > 0

def test_disk_info():
    resp = client.post("/v1/execute", json={"tool_id": "system.disk", "params": {}})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "partitions" in data
    assert len(data["partitions"]) > 0
    p = data["partitions"][0]
    assert "mountpoint" in p
    assert "total" in p
    assert "used" in p
    assert "free" in p
    assert "percent" in p

def test_network_info():
    resp = client.post("/v1/execute", json={"tool_id": "system.network", "params": {}})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "bytes_sent" in data
    assert "bytes_recv" in data
    assert isinstance(data["bytes_sent"], int)
    assert isinstance(data["bytes_recv"], int)

def test_processes():
    resp = client.post("/v1/execute", json={"tool_id": "system.processes", "params": {}})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "processes" in data
    assert len(data["processes"]) > 0
    p = data["processes"][0]
    assert "pid" in p
    assert "name" in p
    assert "cpu_percent" in p
