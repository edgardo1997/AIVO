import os
import pytest
import tempfile
from fastapi.testclient import TestClient
from main import app
from modules.permissions import _svc as perm_svc

client = TestClient(app)


def admin_mode():
    perm_svc.set_level("admin")


def test_list_root():
    admin_mode()
    resp = client.post("/v1/execute", json={"tool_id": "filesystem.list", "params": {"path": "C:\\"}})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "path" in data
    assert "entries" in data


def test_list_temp():
    admin_mode()
    resp = client.post("/v1/execute", json={"tool_id": "filesystem.list", "params": {"path": tempfile.gettempdir()}})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "path" in data
    assert "entries" in data


def test_read_file():
    admin_mode()
    test_file = os.path.join(tempfile.gettempdir(), "aivo_test_read.txt")
    with open(test_file, "w") as f:
        f.write("test content 123")
    try:
        resp = client.post("/v1/execute", json={"tool_id": "filesystem.read", "params": {"path": test_file}})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "content" in data
        assert "test content" in data["content"]
    finally:
        if os.path.exists(test_file):
            os.remove(test_file)


def test_write_file():
    admin_mode()
    test_file = os.path.join(tempfile.gettempdir(), "aivo_test_write.txt")
    try:
        resp = client.post(
            "/v1/execute",
            json={"tool_id": "filesystem.write", "params": {"path": test_file, "content": "written content"}},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "size" in data
        with open(test_file) as f:
            assert f.read() == "written content"
    finally:
        if os.path.exists(test_file):
            os.remove(test_file)


def test_search():
    admin_mode()
    tmp = tempfile.gettempdir()
    resp = client.post("/v1/execute", json={"tool_id": "filesystem.search", "params": {"query": "tmp", "root": tmp}})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "results" in data


def test_search_with_extension():
    admin_mode()
    tmp = tempfile.gettempdir()
    resp = client.post("/v1/execute", json={"tool_id": "filesystem.search", "params": {"query": ".log", "root": tmp}})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "results" in data
