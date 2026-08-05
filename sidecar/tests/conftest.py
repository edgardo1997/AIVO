import pytest
import os
import sys
import json
import shutil
import tempfile
from fastapi.testclient import TestClient
from unittest.mock import patch

os.environ["SENTINEL_ENABLE_ACL"] = "0"
os.environ["SENTINEL_ENABLE_FLEET_STARTUP"] = "0"
os.environ.setdefault("SENTINEL_JWT_SECRET", "sentinel-test-jwt-secret-not-for-production")
_test_data_dir = tempfile.mkdtemp(prefix="sentinel-tests-")
os.environ["SENTINEL_DB_PATH"] = os.path.join(_test_data_dir, "sentinel-test.db")
os.environ["AIVO_DB_PATH"] = os.environ["SENTINEL_DB_PATH"]
os.environ["SENTINEL_PRODUCT_DIR"] = os.path.join(_test_data_dir, "product")
os.environ["SENTINEL_DATA_DIR"] = os.path.join(_test_data_dir, "data")
os.environ["SENTINEL_CACHE_DIR"] = os.path.join(_test_data_dir, "cache")
os.environ["SENTINEL_CONFIG_DIR"] = os.path.join(_test_data_dir, "config")
os.environ["SENTINEL_MODEL_DIR"] = os.path.join(_test_data_dir, "models")
os.environ["LOCALAPPDATA"] = _test_data_dir
os.environ["APPDATA"] = _test_data_dir
os.environ["HOME"] = _test_data_dir
os.environ["USERPROFILE"] = _test_data_dir
_sidecar_dir = os.path.join(os.path.dirname(__file__), "..")
_aivo_dir = os.path.join(_sidecar_dir, "..")
sys.path.insert(0, os.path.abspath(_sidecar_dir))
sys.path.insert(0, os.path.abspath(_aivo_dir))

from main import app, _rate_limiter, initialize_runtime
from modules.auth import IdentityContext
from modules.permissions import _svc as perm_svc

import windows_acl
import repositories.database as db_mod

windows_acl.ACL_ENABLED = False
db_mod._TESTING = True

app.state._test_mode = True
app.state._test_secret = "valid-test-token"

TEST_IDENTITY = IdentityContext.test_identity().to_dict()


@pytest.fixture(scope="session", autouse=True)
def initialized_test_runtime():
    """Tests opt into runtime registration instead of relying on import side effects."""
    initialize_runtime()


def _reset_tool_rate_limiter(orchestrator):
    """Reset per-tool sliding windows so one test cannot starve the rest.

    pytest-benchmark iterates process/execute calls many times, which can
    exhaust the ToolExecutionGuard's per-tool budget (e.g. process.* 20/60s)
    and cascade 403s into every later test that calls /api/sentinel/process.
    """
    from sentinel.security.tool_rate_limiter import ToolRateLimiter

    guard = getattr(getattr(orchestrator, "_execution_pipeline", None), "_guard", None)
    router = getattr(orchestrator, "_model_router", None)
    if guard is None and router is not None:
        guard = getattr(router, "_tool_guard", None)
    if guard is None:
        return
    rl = getattr(guard, "_rate_limiter", None)
    if isinstance(rl, ToolRateLimiter):
        rl.reset()


def admin_mode():
    perm_svc.set_level("admin")


def confirm_mode():
    perm_svc.set_level("confirm")


@pytest.fixture(scope="session", autouse=True)
def isolated_test_database():
    """Keep the entire test session away from the user's persistent database."""
    from repositories.database import DatabaseManager, PRODUCTION_DB_PATH

    db = DatabaseManager()
    assert os.path.normcase(os.path.abspath(db.db_path)) != os.path.normcase(PRODUCTION_DB_PATH)
    yield
    db.close()
    shutil.rmtree(_test_data_dir, ignore_errors=True)


@pytest.fixture(autouse=True)
def clean_state():
    perm_svc.pending_actions.clear()
    perm_svc.emergency_stop_flag = False
    _rate_limiter.clear()
    default_perms = {"level": "confirm", "allowlist": [], "blocklist": [], "auto_safe": True}
    from repositories.database import DatabaseManager

    db = DatabaseManager()
    db.config_set_json("permissions", default_perms)
    db.config_set_json(
        "fleet_config",
        {
            "remote_enabled": False,
            "pairing_token": "",
            "pairing_token_hash": "",
            "local_ip": "",
            "api_port": 8765,
            "fleet_port": 8766,
        },
    )
    db.config_set_json(
        "ai_config",
        {"provider": "openrouter", "api_key": "", "model": "gpt-4o", "base_url": ""},
    )
    try:
        from modules.ai_provider import _svc as ai_svc

        if getattr(ai_svc, "_router", None) is not None:
            ai_svc.restore_config()
            ai_svc.load_provider_keys()
    except Exception:
        pass
    try:
        from modules.sentinel_bridge import get_orchestrator

        orch = get_orchestrator()
        rl = getattr(orch, "_rate_limiter", None)
        if rl is not None:
            rl.clear()
        _reset_tool_rate_limiter(orch)
    except Exception:
        pass
    try:
        from modules.sentinel_bridge import get_memory

        mem = get_memory()
        if mem is not None:
            mem.clear()
    except Exception:
        pass
    yield


@pytest.fixture(autouse=True)
def disable_external_model_probes(monkeypatch):
    """Unit and integration tests must never discover services on the host."""
    from sentinel.core.model_router import ModelRouter

    monkeypatch.setattr(
        ModelRouter,
        "check_health",
        lambda self, provider_id, timeout=0.75: {
            "provider_id": provider_id,
            "available": False,
            "reason": "disabled_in_tests",
        },
    )


@pytest.fixture
def client():
    with TestClient(app) as tc:
        tc.headers.update({"X-Test-Token": "valid-test-token"})
        yield tc


@pytest.fixture
def temp_config(tmp_path):
    old = os.environ.get("AIVO_CONFIG")
    cfg = {"provider": "openrouter", "api_key": "test-key", "model": "test-model", "base_url": "http://test"}
    path = str(tmp_path / "aivo-test-config.json")
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


_OFFICIAL_MARKERS = {
    "unit",
    "contract",
    "integration",
    "security",
    "adversarial",
    "e2e",
    "e2e_real",
    "performance",
    "stability",
    "smoke",
    "build",
    "legacy",
    "experimental",
    "alpha_constitutional_gate",
    "local_runtime",
    "production",
    "stress",
    "chaos",
}


def _infer_marker(nodeid: str) -> str | None:
    """Infer a primary marker from the test file path.

    This is a coarse classifier; it does not replace explicit markers on tests.
    """
    name = nodeid.lower().replace("\\", "/")
    if "tests/security/" in name or "tests/runtime/security" in name:
        return "security"
    if "tests/observability/" in name:
        return "stability"
    if "tests/storage/" in name:
        return "integration"
    if "tests/runtime/" in name:
        return "integration"
    if "tests/intelligence/" in name:
        return "unit"
    if "_e2e_real" in name:
        return "e2e_real"
    if "_e2e" in name:
        return "e2e"
    if "_adversarial" in name or "_pentest" in name:
        return "adversarial"
    if "_security" in name or "_hardening" in name or "_toctou" in name or "_execution_bypass" in name or "_secret_redaction" in name:
        return "security"
    if "_contract" in name or "_durable_" in name or "_fase2_" in name:
        return "contract"
    if "_benchmark" in name or "_phase8" in name or "_performance" in name or "_stability" in name:
        return "performance"
    if "_integration" in name or "_conversation_" in name or "_chat_" in name or "_live_" in name or "_sidecar_" in name or "_filesystem" in name or "_bootstrap" in name:
        return "integration"
    if "_alpha_" in name or "_constitutional" in name or "_ambiguity" in name:
        return "alpha_constitutional_gate"
    if "_unit" in name:
        return "unit"
    # Default for unmarked tests under tests/ that do not match a specific pattern
    if "tests/" in name:
        return "unit"
    return None


def pytest_collection_modifyitems(config, items):
    """Track unmarked tests and tag them so the suite can be audited."""
    unmarked = []
    for item in items:
        if not any(m.name in _OFFICIAL_MARKERS for m in item.own_markers):
            inferred = _infer_marker(item.nodeid)
            if inferred:
                item.add_marker(inferred)
            else:
                item.add_marker("legacy")
                unmarked.append(item.nodeid)
    if unmarked:
        # Warnings are printed but the suite still runs. CI can fail with -W error::UserWarning if desired.
        import warnings

        warnings.warn(f"{len(unmarked)} tests have no official marker and were tagged as legacy")


def pytest_sessionfinish(session, exitstatus):
    """Fail the session if CI demands fully classified tests."""
    if os.environ.get("SENTINEL_FAIL_UNMARKED") and session.config.getoption("--collect-only") is None:
        # This is intentionally simple: the gate is enforced by CI, not by default local runs.
        if any(True for item in session.items if any(m.name == "legacy" for m in item.own_markers)):
            session.exitstatus = 1
