from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_system_info():
    resp = client.get("/api/monitor/system")
    assert resp.status_code == 200
    data = resp.json()
    assert "hostname" in data
    assert "os" in data
    assert "cpu" in data
    assert "memory" in data

def test_cpu_info():
    resp = client.get("/api/monitor/cpu")
    assert resp.status_code == 200
    data = resp.json()
    assert "percent" in data
    assert "cores" in data
    assert data["cores"]["physical"] >= 1
    assert data["cores"]["logical"] >= 1

def test_memory_info():
    resp = client.get("/api/monitor/memory")
    assert resp.status_code == 200
    data = resp.json()
    assert "percent" in data
    assert "total" in data
    assert "used" in data
    assert "available" in data
    assert 0 <= data["percent"] <= 100
    assert data["total"] > 0

def test_disk_info():
    resp = client.get("/api/monitor/disk")
    assert resp.status_code == 200
    data = resp.json()
    assert "partitions" in data
    assert len(data["partitions"]) > 0
    p = data["partitions"][0]
    assert "mount" in p
    assert "total" in p
    assert "used" in p
    assert "free" in p
    assert "percent" in p

def test_network_info():
    resp = client.get("/api/monitor/network")
    assert resp.status_code == 200
    data = resp.json()
    assert "bytes_sent" in data
    assert "bytes_recv" in data
    assert isinstance(data["bytes_sent"], int)
    assert isinstance(data["bytes_recv"], int)

def test_processes():
    resp = client.get("/api/monitor/processes")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) > 0
    p = data[0]
    assert "pid" in p
    assert "name" in p
    assert "cpu_percent" in p
    assert "memory_percent" in p
