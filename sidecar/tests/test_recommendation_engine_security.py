import ast
from pathlib import Path
from typing import get_args

from sentinel.contracts import DecisionResultV1
from sentinel.recommendation_engine import (
    RecommendationResultV1,
    RecommendationValue,
)

ROOT = Path(__file__).parents[2] / "sentinel" / "recommendation_engine"


def test_package_has_no_productive_imports_or_execution_calls():
    forbidden_imports = {
        "multiprocessing",
        "socket",
        "subprocess",
        "threading",
        "sentinel.core.orchestrator",
        "sentinel.core.planner",
        "sentinel.core.tool_gateway",
        "sidecar.services.executor_service",
    }
    forbidden_calls = {
        "Popen",
        "execute",
        "launch",
        "run",
        "startfile",
        "system",
    }
    for path in ROOT.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
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
        assert imports.isdisjoint(forbidden_imports), path.name
        assert calls.isdisjoint(forbidden_calls), path.name


def test_results_are_non_authoritative_contracts():
    assert issubclass(RecommendationResultV1, DecisionResultV1)
    assert get_args(RecommendationResultV1.model_fields["authority"].annotation) == (False,)
    assert get_args(RecommendationResultV1.model_fields["execution_requested"].annotation) == (False,)


def test_recommendation_vocabulary_contains_no_operational_actions():
    forbidden = {"EXECUTE", "RUN", "ACTIVATE", "AUTHORIZE", "CUTOVER", "MIGRATE"}
    assert {item.value for item in RecommendationValue}.isdisjoint(forbidden)
