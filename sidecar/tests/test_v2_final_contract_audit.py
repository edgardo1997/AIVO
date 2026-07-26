from sentinel.activation_gateway.decision import AuthoritySelectionDecisionV1
from sentinel.contracts import (
    AuditEventV1,
    DecisionResultV1,
    EvidenceSignalV1,
    HealthStatusV1,
    ReadinessResultV1,
)
from sentinel.final_control_plane_readiness.decision import (
    FinalReadinessDecision,
)
from sentinel.runtime_replay_validation.replay import ReplayExecutionResultV1
from sentinel.runtime_trial.trial import RuntimeTrialResult
from sentinel.runtime_v2_controlled.diagnostics import RuntimeShadowResultV1
from sentinel.v2_authority_readiness.validator import (
    AuthorityReadinessResultV1,
)


def test_central_contracts_are_available_and_non_authoritative():
    for contract in (
        AuditEventV1,
        EvidenceSignalV1,
        HealthStatusV1,
        ReadinessResultV1,
    ):
        assert contract.model_fields["authority"].default is False
        assert contract.model_fields["execution_requested"].default is False


def test_primary_consolidated_results_use_decision_result():
    for result in (
        AuthoritySelectionDecisionV1,
        FinalReadinessDecision,
        RuntimeTrialResult,
        AuthorityReadinessResultV1,
    ):
        assert issubclass(result, DecisionResultV1)


def test_audit_records_known_contract_gaps_without_hiding_them():
    assert not issubclass(ReplayExecutionResultV1, DecisionResultV1)
    assert not issubclass(RuntimeShadowResultV1, DecisionResultV1)
    assert "execution_requested" not in ReplayExecutionResultV1.model_fields
    assert "execution_requested" not in RuntimeShadowResultV1.model_fields
