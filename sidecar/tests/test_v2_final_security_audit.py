import ast
from pathlib import Path

ROOT = Path(__file__).parents[2] / "sentinel"
V2_PACKAGES = (
    "activation_gateway",
    "application_discovery_v2",
    "authority_safety_layer",
    "authorization_canary",
    "canary_environment",
    "canary_observation",
    "controlled_runtime_activation",
    "cutover_validation",
    "decision_long_term_evaluation",
    "decision_shadow_validation",
    "evidence_integrity",
    "final_control_plane_readiness",
    "operational_telemetry_hub",
    "persistent_control_boundary",
    "policy_v2_shadow",
    "promotion_validation",
    "runtime_canary",
    "runtime_equivalence_validation",
    "runtime_replay_validation",
    "runtime_trial",
    "runtime_v2_controlled",
    "shadow",
    "stability_validation",
    "v2_authority_migration",
    "v2_authority_readiness",
    "v2_operational_evidence_storage",
    "v2_operational_observability",
    "v2_trust_evaluation",
)


def _files():
    for package in V2_PACKAGES:
        yield from (ROOT / package).glob("*.py")


def test_no_v2_module_requests_authority_or_execution():
    for path in _files():
        source = path.read_text(encoding="utf-8")
        assert "authority=True" not in source
        assert "execution_requested=True" not in source
        if "contract_adapters" not in path.parts:
            assert "action_requested" not in source
            assert "authority_explicit" not in source


def test_no_v2_module_spawns_processes_or_shells():
    forbidden_calls = {
        "Popen",
        "system",
        "create_subprocess_exec",
        "create_subprocess_shell",
    }
    for path in _files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        calls = {
            node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, (ast.Attribute, ast.Name))
        }
        assert calls.isdisjoint(forbidden_calls)
