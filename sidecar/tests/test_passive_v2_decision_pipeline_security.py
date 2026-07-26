import ast
from pathlib import Path

import pytest
from pydantic import ValidationError

from sentinel.final_control_plane_readiness.passive_pipeline import (
    PassiveDecisionPipelineResult,
)

MODULE = Path(__file__).parents[2] / "sentinel" / "final_control_plane_readiness" / "passive_pipeline.py"


def test_pipeline_has_no_productive_runtime_dependencies_or_calls():
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    imports = set()
    calls = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                calls.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                calls.add(node.func.attr)

    forbidden_imports = {
        "subprocess",
        "sentinel.core.orchestrator",
        "sentinel.core.planner",
        "sentinel.core.tool_gateway",
        "sidecar.services.executor_service",
    }
    assert imports.isdisjoint(forbidden_imports)
    assert calls.isdisjoint({"execute", "launch", "Popen", "run", "system", "startfile"})


def test_pipeline_result_cannot_request_authority_or_execution():
    with pytest.raises(ValidationError):
        PassiveDecisionPipelineResult.model_validate(
            {
                "status": "SIGNATURE_REJECTED",
                "correlation_id": "decision:x",
                "decision": {
                    "correlation_id": "decision:x",
                    "evidence_hash": "0" * 64,
                    "issuer_id": "issuer",
                    "timestamp": "2026-01-01T00:00:00Z",
                    "decision_state": "OBSERVE",
                },
                "authority": True,
            }
        )
    with pytest.raises(ValidationError):
        PassiveDecisionPipelineResult.model_validate(
            {
                "status": "SIGNATURE_REJECTED",
                "correlation_id": "decision:x",
                "decision": {
                    "correlation_id": "decision:x",
                    "evidence_hash": "0" * 64,
                    "issuer_id": "issuer",
                    "timestamp": "2026-01-01T00:00:00Z",
                    "decision_state": "OBSERVE",
                },
                "execution_requested": True,
            }
        )
