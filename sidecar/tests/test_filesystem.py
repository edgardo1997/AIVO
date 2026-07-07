import pytest
import os
import tempfile
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_list_root():
    resp = client.get("/api/fs/list?path=C:\\")
    assert resp.status_code == 200
    data = resp.json()
    assert "path" in data
    assert "entries" in data
    assert len(data["entries"]) > 0

def test_list_current_dir():
    resp = client.get(f"/api/fs/list?path={os.getcwd()}")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["entries"]) > 0
    # Should contain Python files
    names = [e["name"] for e in data["entries"]]
    assert "main.py" in names or "conftest.py" in names

def test_read_file():
    test_file = os.path.join(tempfile.gettempdir(), "aivo_test_read.txt")
    with open(test_file, "w") as f:
        f.write("test content 123")
    try:
        resp = client.post("/api/fs/read", json={"path": test_file})
        assert resp.status_code == 200
        data = resp.json()
        assert "content" in data
        assert "test content" in data["content"]
    finally:
        if os.path.exists(test_file):
            os.remove(test_file)

def test_write_file():
    test_file = os.path.join(tempfile.gettempdir(), "aivo_test_write.txt")
    try:
        resp = client.post("/api/fs/write", json={"path": test_file, "content": "written content"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "saved"
        with open(test_file) as f:
            assert f.read() == "written content"
    finally:
        if os.path.exists(test_file):
            os.remove(test_file)

def test_search():
    resp = client.get("/api/fs/search?query=main.py")
    assert resp.status_code == 200
    data = resp.json()
    assert "results" in data
    assert len(data["results"]) > 0

def test_search_with_extension():
    resp = client.get("/api/fs/search?query=*.py")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["results"]) > 0
    assert any(r.endswith(".py") for r in data["results"])
