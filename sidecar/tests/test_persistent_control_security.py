import ast
import sqlite3
from pathlib import Path

from sentinel.persistent_control_boundary import PersistentControlBoundary

BOUNDARY_ROOT = Path(__file__).parents[2] / "sentinel" / "persistent_control_boundary"
FORBIDDEN_IMPORTS = {
    "executor",
    "tool_gateway",
    "orchestrator",
    "planner",
    "policy_engine",
    "decision_engine",
    "subprocess",
}
FORBIDDEN_CALLS = {"launch", "Popen", "system"}


def test_boundary_has_no_runtime_dependencies_or_execution_calls():
    for path in BOUNDARY_ROOT.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        calls = {
            node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, (ast.Attribute, ast.Name))
        }
        assert not any(forbidden in imported for imported in imports for forbidden in FORBIDDEN_IMPORTS)
        assert calls.isdisjoint(FORBIDDEN_CALLS)
        assert "authority=True" not in path.read_text(encoding="utf-8")
        assert "execution_requested=True" not in path.read_text(encoding="utf-8")


def test_sql_is_parameterized_and_schema_contains_no_sensitive_fields():
    source = "\n".join(path.read_text(encoding="utf-8") for path in BOUNDARY_ROOT.glob("*.py"))
    for forbidden in ("prompt", "command", "secret", "executable_argument"):
        assert forbidden not in source.lower()
    assert 'f"SELECT' not in source
    assert 'f"INSERT' not in source
    assert 'f"UPDATE' not in source
    assert 'f"DELETE' not in source


def test_audit_contains_only_sanitized_control_fields(tmp_path):
    path = tmp_path / "boundary.sqlite3"
    boundary = PersistentControlBoundary(database_path=path, enabled=True)
    boundary.transaction.create(
        correlation_id="request-1",
        evidence_hash="f" * 64,
        issuer_id="issuer.boundary.v1",
        signature="s" * 88,
    )
    boundary.close()

    connection = sqlite3.connect(path)
    columns = {row[1] for row in connection.execute("PRAGMA table_info(control_audit)")}
    connection.close()
    assert columns == {
        "audit_id",
        "event",
        "timestamp",
        "correlation_id",
        "evidence_hash",
        "previous_state",
        "new_state",
        "result",
    }
