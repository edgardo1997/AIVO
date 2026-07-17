import pytest
import os
import sys
import json
import tempfile
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from main import app
from modules.permissions import PENDING_ACTIONS

@pytest.fixture(autouse=True)
def clean_state():
    PENDING_ACTIONS.clear()
    yield

@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture
def temp_config():
    old = os.environ.get("AIVO_CONFIG")
    cfg = {"provider": "openrouter", "api_key": "test-key", "model": "test-model", "base_url": "http://test"}
    path = os.path.join(tempfile.gettempdir(), ".aivo_test_config.json")
    with open(path, "w") as f:
        json.dump(cfg, f)
    os.environ["AIVO_CONFIG"] = path
    yield path
    if old is None:
        del os.environ["AIVO_CONFIG"]
    else:
        os.environ["AIVO_CONFIG"] = old
    if os.path.exists(path):
        os.remove(path)
