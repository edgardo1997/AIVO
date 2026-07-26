import ast
from pathlib import Path

ROOT = Path(__file__).parents[2] / "sentinel"
PACKAGES = (
    "v2_operational_observability",
    "v2_operational_evidence_storage",
    "persistent_control_boundary",
    "final_control_plane_readiness",
    "v2_trust_evaluation",
    "controlled_runtime_activation",
    "operational_telemetry_hub",
)


def test_reports_are_pure_presenters_without_decision_or_action_methods():
    for package in PACKAGES:
        path = ROOT / package / "report.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        methods = {node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        assert methods.isdisjoint({"evaluate", "decide", "activate", "execute", "launch", "route"})


def test_reports_do_not_import_runtime_or_authority_engines():
    for package in PACKAGES:
        path = ROOT / package / "report.py"
        source = path.read_text(encoding="utf-8")
        for forbidden in (
            "Executor",
            "ToolGateway",
            "Orchestrator",
            "PolicyEngine",
            "DecisionEngine",
        ):
            assert forbidden not in source
