import ast
from pathlib import Path

from sentinel.operational_telemetry_hub import OperationalMetricSnapshotV1

ROOT = Path(__file__).parents[2] / "sentinel"
LOCAL_METRICS = (
    "v2_operational_observability/metrics.py",
    "v2_operational_evidence_storage/metrics.py",
    "persistent_control_boundary/metrics.py",
    "final_control_plane_readiness/metrics.py",
    "v2_trust_evaluation/metrics.py",
    "controlled_runtime_activation/metrics.py",
)


def test_operational_metric_snapshot_is_the_persistent_boundary():
    fields = set(OperationalMetricSnapshotV1.model_fields)
    assert {"authority", "execution_requested"} <= fields
    assert not fields.intersection({"payload", "command", "path", "prompt", "tool", "arguments"})


def test_local_metrics_are_in_memory_counters_only():
    for relative in LOCAL_METRICS:
        path = ROOT / relative
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        assert "sqlite3" not in imports
        assert "pathlib" not in imports
        source = path.read_text(encoding="utf-8").lower()
        assert "prompt" not in source
        assert "command" not in source
