import ast
from pathlib import Path

from sentinel.authority_safety_layer import (
    AuthoritySafetyMetrics,
    AuthoritySafetyReport,
    RecoveryStatus,
    SafetyOperationRecord,
)


ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "sentinel" / "authority_safety_layer"
FORBIDDEN_IMPORTS = {
    "subprocess",
    "sentinel.core.orchestrator",
    "sentinel.core.tool_gateway",
    "sentinel.core.planner",
    "sentinel.core.policy_engine",
    "sentinel.core.decision_engine",
    "sidecar.services.executor_service",
}
FORBIDDEN_CALLS = {"launch", "popen", "system", "AuthorizationGrantV1"}


def trees():
    return [(path, ast.parse(path.read_text(encoding="utf-8"))) for path in MODULE.glob("*.py")]


def test_no_forbidden_imports_or_system_execution() -> None:
    violations = []
    for path, tree in trees():
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                names = []
            if any(name.startswith(forbidden) for name in names for forbidden in FORBIDDEN_IMPORTS):
                violations.append(f"{path.name}:{node.lineno}:import")
            if isinstance(node, ast.Call):
                name = (
                    node.func.attr
                    if isinstance(node.func, ast.Attribute)
                    else node.func.id
                    if isinstance(node.func, ast.Name)
                    else ""
                )
                if name in FORBIDDEN_CALLS:
                    violations.append(f"{path.name}:{node.lineno}:{name}")
                if name == "execute" and path.name not in {
                    "storage.py",
                    "audit_store.py",
                }:
                    violations.append(f"{path.name}:{node.lineno}:execute")
    assert violations == []


def test_persisted_model_has_no_sensitive_or_executable_fields() -> None:
    fields = set(SafetyOperationRecord.model_fields)
    assert SafetyOperationRecord.model_fields["authority"].default is False
    assert fields.isdisjoint(
        {
            "user",
            "prompt",
            "command",
            "path",
            "arguments",
            "secret",
            "parameters",
            "executable",
        }
    )


def test_metrics_and_report_are_aggregate_only() -> None:
    metrics = AuthoritySafetyMetrics()
    metrics.increment("operations_started")
    metrics.increment("recovery_required")
    snapshot = metrics.snapshot()
    assert snapshot.operations_started == 1
    assert snapshot.recovery_required == 1
    assert not hasattr(metrics, "operations")
    report = AuthoritySafetyReport(
        recovery=RecoveryStatus.RECOVERY_REQUIRED,
        metrics=snapshot,
        risks=("PENDING_MIGRATION",),
        recommendation="KEEP_LEGACY_AUTHORITY",
    )
    assert report.human_readable().startswith("SENTINEL PERSISTENT AUTHORITY SAFETY REPORT")


def test_productive_runtime_does_not_import_safety_layer() -> None:
    offenders = []
    for folder in (ROOT / "sentinel" / "core", ROOT / "sidecar" / "services"):
        if folder.exists():
            for path in folder.rglob("*.py"):
                if "sentinel.authority_safety_layer" in path.read_text(
                    encoding="utf-8",
                    errors="ignore",
                ):
                    offenders.append(str(path))
    assert offenders == []
