import ast
from pathlib import Path

import pytest

from sentinel.activation_gateway.decision import AuthoritySelectionDecisionV1
from sentinel.authority_safety_layer.state import SafetyOperationRecord
from sentinel.canary_environment.environment import CanaryEnvironmentV1
from sentinel.controlled_runtime_activation.router import RuntimeRouteDecisionV1
from sentinel.contracts import DecisionResultV1
from sentinel.decision_long_term_evaluation.window import EvaluationWindowV1
from sentinel.decision_shadow_validation.validator import DecisionShadowResultV1
from sentinel.final_control_plane_readiness.decision import (
    FinalReadinessDecision,
)
from sentinel.runtime_equivalence_validation.validator import (
    RuntimeEquivalenceResultV1,
)
from sentinel.runtime_trial.trial import RuntimeTrialResult, RuntimeTrialV1
from sentinel.v2_authority_migration.router import AuthorityDecision
from sentinel.v2_authority_readiness.validator import (
    AuthorityReadinessResultV1,
)
from sentinel.v2_operational_observability.observer import ObservationResultV1
from sentinel.v2_trust_evaluation.evaluator import TrustEvaluationResultV1
from sentinel.v2_trust_evaluation.recommendation import TrustRecommendationV1

ROOT = Path(__file__).parents[2]
PACKAGES = (
    "canary_environment",
    "runtime_trial",
    "decision_shadow_validation",
    "decision_long_term_evaluation",
    "v2_authority_readiness",
    "v2_authority_migration",
    "authority_safety_layer",
    "runtime_equivalence_validation",
    "activation_gateway",
    "controlled_runtime_activation",
    "v2_operational_observability",
    "v2_operational_evidence_storage",
    "v2_trust_evaluation",
    "final_control_plane_readiness",
)
MIGRATED_RESULTS = (
    CanaryEnvironmentV1,
    RuntimeTrialV1,
    RuntimeTrialResult,
    DecisionShadowResultV1,
    EvaluationWindowV1,
    AuthorityReadinessResultV1,
    AuthorityDecision,
    SafetyOperationRecord,
    RuntimeEquivalenceResultV1,
    AuthoritySelectionDecisionV1,
    RuntimeRouteDecisionV1,
    ObservationResultV1,
    TrustEvaluationResultV1,
    TrustRecommendationV1,
    FinalReadinessDecision,
)
FORBIDDEN_IMPORTS = {
    "executor_service",
    "tool_gateway",
    "orchestrator",
    "core.planner",
    "core.policy_engine",
    "core.decision_engine",
    "subprocess",
}
FORBIDDEN_CALLS = {"launch", "Popen", "system"}


@pytest.mark.parametrize("model", MIGRATED_RESULTS)
def test_migrated_results_share_central_non_authority_contract(model):
    assert issubclass(model, DecisionResultV1)
    assert model.model_fields["authority"].default is False
    assert model.model_fields["execution_requested"].default is False
    assert "action_requested" not in model.model_fields
    assert "authority_explicit" not in model.model_fields


def test_old_authority_aliases_do_not_exist_in_v2_consumers():
    for package in PACKAGES:
        for path in (ROOT / "sentinel" / package).glob("*.py"):
            source = path.read_text(encoding="utf-8")
            assert "action_requested" not in source
            assert "authority_explicit" not in source


def test_v2_consumers_do_not_import_productive_runtime_or_execute():
    for package in PACKAGES:
        for path in (ROOT / "sentinel" / package).glob("*.py"):
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
            unsafe_execute_calls = [
                node
                for node in ast.walk(tree)
                if isinstance(node, ast.Call)
                and (
                    isinstance(node.func, ast.Name)
                    and node.func.id == "execute"
                    or isinstance(node.func, ast.Attribute)
                    and node.func.attr == "execute"
                    and not _is_sql_receiver(node.func.value)
                )
                and not _is_limited_canary_receiver(path, node.func)
            ]
            assert not any(forbidden in imported for imported in imports for forbidden in FORBIDDEN_IMPORTS)
            assert calls.isdisjoint(FORBIDDEN_CALLS)
            assert not unsafe_execute_calls


def _is_sql_receiver(node: ast.expr) -> bool:
    if isinstance(node, ast.Name):
        return node.id == "cursor"
    if isinstance(node, ast.Attribute):
        return node.attr in {"connection", "_connection"}
    return False


def _is_limited_canary_receiver(path: Path, node: ast.expr) -> bool:
    return (
        path.name == "canary_execution.py"
        and isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Attribute)
        and isinstance(node.value.value, ast.Name)
        and node.value.value.id == "self"
        and node.value.attr == "v2_executor"
    )
