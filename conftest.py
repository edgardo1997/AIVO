"""Repository-wide deterministic test classification and resource checks."""

from __future__ import annotations

import time
from pathlib import Path

import pytest


SECURITY_FILES = {
    "test_adversarial_security.py",
    "test_auth_authorization.py",
    "test_path_guardian.py",
    "test_pentest_gate.py",
    "test_permissions.py",
    "test_production_security.py",
    "test_security_verification.py",
    "test_trust_pipeline_invariants.py",
    "test_unified_confirmation.py",
    "test_windows_acl.py",
}
INTEGRATION_TOKENS = ("integration", "_api", "workflow", "bootstrap", "desktop_integrations")


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Give every test exactly one independently executable suite marker."""
    for item in items:
        existing_markers = {marker.name for marker in item.iter_markers()}
        if "performance" in existing_markers:
            continue
        filename = Path(str(item.path)).name
        if filename == "test_benchmarks.py":
            marker = "performance"
        elif filename.startswith("test_e2e_"):
            marker = "e2e"
        elif filename in SECURITY_FILES:
            marker = "security"
        elif any(token in filename for token in INTEGRATION_TOKENS):
            marker = "integration"
        else:
            marker = "unit"
        if marker not in existing_markers:
            item.add_marker(getattr(pytest.mark, marker))


@pytest.fixture(scope="session", autouse=True)
def no_leaked_child_processes():
    """Fail when the suite leaves a child process alive after teardown."""
    try:
        import psutil
    except ImportError:
        yield
        return

    parent = psutil.Process()
    before = {child.pid for child in parent.children(recursive=True)}
    yield
    leaked = [child for child in parent.children(recursive=True) if child.pid not in before and child.is_running()]
    for child in leaked:
        child.terminate()
    if leaked:
        _, alive = psutil.wait_procs(leaked, timeout=3)
        for child in alive:
            child.kill()
        time.sleep(0.05)
        pytest.fail(f"Test suite leaked child processes: {[child.pid for child in leaked]}", pytrace=False)
