import pytest
from pydantic import ValidationError

from sentinel.contracts import (
    EvidenceIntegrityStatusV1,
    PolicyEvaluationStatusV1,
    SimulationActionTypeV1,
)
from sentinel.operational_telemetry_hub import OperationalTelemetryHub
from sentinel.policy_engine import PassivePolicyEngine, PolicyEngineControl
from sentinel.recommendation_engine import RiskLevel
from sentinel.simulation_engine import PassiveSimulationEngine, SimulationEngineControl
from test_simulation_engine import _contracts


def _policy_inputs(tmp_path, *, risk=RiskLevel.MEDIUM, action=None):
    contracts = _contracts(risk)
    simulation_telemetry = OperationalTelemetryHub(
        database_path=tmp_path / "simulation-source.sqlite3",
        enabled=True,
    )
    simulator = PassiveSimulationEngine(
        control=SimulationEngineControl(enabled=True),
        telemetry_hub=simulation_telemetry,
    )
    envelope = simulator.simulate(
        action_type=action or SimulationActionTypeV1.DELETE_FILE,
        target_class="SANITIZED_TARGET",
        dependency_classes=(),
        **contracts,
    )
    simulation_telemetry.close()
    return {
        "decision": contracts["decision"],
        "recommendation": contracts["recommendation"],
        "simulation": envelope.simulation,
        "evidence": contracts["evidence"],
        "trust": contracts["trust"],
        "readiness": contracts["readiness"],
        "health": contracts["health"],
    }


def _engine(tmp_path, *, enabled=True):
    telemetry = OperationalTelemetryHub(
        database_path=tmp_path / "policy.sqlite3",
        enabled=True,
    )
    engine = PassivePolicyEngine(
        control=PolicyEngineControl(enabled=enabled),
        telemetry_hub=telemetry,
    )
    return engine, telemetry


def test_policy_evaluation_is_deterministic_and_idempotent(tmp_path):
    inputs = _policy_inputs(tmp_path)
    engine, telemetry = _engine(tmp_path)
    try:
        first = engine.evaluate(**inputs)
        second = engine.evaluate(**inputs)
        assert first.evaluation == second.evaluation
        assert len(telemetry.timeline.latest()) == 1
    finally:
        telemetry.close()


def test_delete_file_requires_human_review_even_when_low_risk(tmp_path):
    inputs = _policy_inputs(tmp_path, risk=RiskLevel.LOW)
    engine, telemetry = _engine(tmp_path)
    try:
        envelope = engine.evaluate(**inputs)
        result = envelope.evaluation
        assert result.policy_status is (PolicyEvaluationStatusV1.POLICY_REVIEW_REQUIRED)
        assert result.requirements == ("HUMAN_REVIEW_REQUIRED",)
        assert result.violations == ()
    finally:
        telemetry.close()


def test_low_risk_reversible_stop_process_is_policy_allowed_not_authorized(
    tmp_path,
):
    inputs = _policy_inputs(
        tmp_path,
        risk=RiskLevel.LOW,
        action=SimulationActionTypeV1.STOP_PROCESS,
    )
    engine, telemetry = _engine(tmp_path)
    try:
        envelope = engine.evaluate(**inputs)
        assert envelope.evaluation.policy_status is (PolicyEvaluationStatusV1.POLICY_ALLOWED)
        assert envelope.evaluation.authority is False
        assert envelope.evaluation.execution_requested is False
    finally:
        telemetry.close()


def test_critical_action_is_blocked_with_explicit_violations(tmp_path):
    inputs = _policy_inputs(tmp_path, risk=RiskLevel.CRITICAL)
    engine, telemetry = _engine(tmp_path)
    try:
        result = engine.evaluate(**inputs).evaluation
        assert result.policy_status is PolicyEvaluationStatusV1.POLICY_BLOCKED
        assert result.violations
        violation = result.violations[0]
        assert violation.rule_id == "CRITICAL_RISK_BLOCK"
        assert violation.description
        assert violation.reason
    finally:
        telemetry.close()


def test_unverified_evidence_produces_unknown_policy(tmp_path):
    inputs = _policy_inputs(tmp_path, risk=RiskLevel.LOW)
    inputs["evidence"] = inputs["evidence"].model_copy(update={"integrity_status": EvidenceIntegrityStatusV1.SIGNED})
    engine, telemetry = _engine(tmp_path)
    try:
        result = engine.evaluate(**inputs).evaluation
        assert result.policy_status is PolicyEvaluationStatusV1.POLICY_UNKNOWN
        assert "VERIFIED_EVIDENCE_REQUIRED" in result.requirements
    finally:
        telemetry.close()


def test_policy_contract_is_immutable_and_rejects_unknown_fields(tmp_path):
    inputs = _policy_inputs(tmp_path)
    engine, telemetry = _engine(tmp_path)
    try:
        result = engine.evaluate(**inputs).evaluation
        with pytest.raises(ValidationError):
            result.confidence = 0
        with pytest.raises(ValidationError):
            result.__class__.model_validate({**result.model_dump(), "unexpected": "value"})
    finally:
        telemetry.close()


def test_policy_evaluation_records_telemetry_and_provenance(tmp_path):
    inputs = _policy_inputs(tmp_path)
    engine, telemetry = _engine(tmp_path)
    try:
        envelope = engine.evaluate(**inputs)
        result = envelope.evaluation
        assert telemetry.timeline.latest() == (envelope.operational_event,)
        assert envelope.telemetry_snapshot is not None
        assert result.correlation_id == inputs["evidence"].correlation_id
        assert result.evidence_hash == inputs["evidence"].payload_hash
        assert result.issuer_id == inputs["evidence"].issuer_id
        assert result.timestamp == inputs["evidence"].created_at
    finally:
        telemetry.close()


def test_policy_engine_is_disabled_by_default(tmp_path):
    telemetry = OperationalTelemetryHub(
        database_path=tmp_path / "disabled.sqlite3",
        enabled=False,
    )
    engine = PassivePolicyEngine(
        control=PolicyEngineControl(environ={}),
        telemetry_hub=telemetry,
    )
    assert engine.evaluate(**_policy_inputs(tmp_path / "source")) is None
    assert not (tmp_path / "disabled.sqlite3").exists()
