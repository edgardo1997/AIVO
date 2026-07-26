from dataclasses import replace

from sentinel.v2_authority_readiness import (
    V2_AUTHORITY_READINESS_ENABLED,
    AuthorityReadinessState,
    ReadinessEvidenceV1,
    V2AuthorityReadinessControl,
    V2AuthorityReadinessEngine,
)


def ready_evidence() -> ReadinessEvidenceV1:
    return ReadinessEvidenceV1(
        contracts_available=True,
        versions_compatible=True,
        critical_contract_gaps=0,
        shadow_match_rate=0.995,
        critical_divergences=0,
        conversion_errors=0,
        identity_available=True,
        authorization_consistent=True,
        replay_detected=False,
        resolver_evidence_valid=True,
        completed_long_windows=3,
        error_rate=0.001,
        maximum_latency_ms=100,
        lost_events=0,
        direct_tool_execution=False,
        gateway_bypass=False,
        hidden_authority=False,
    )


def test_disabled_by_default_does_not_evaluate() -> None:
    assert V2_AUTHORITY_READINESS_ENABLED is False
    engine = V2AuthorityReadinessEngine(control=V2AuthorityReadinessControl(environ={}))
    assert engine.evaluate(ready_evidence()) is None
    assert engine.metrics.snapshot().validation_runs == 0


def test_all_gates_pass_only_approves_future_consideration() -> None:
    engine = V2AuthorityReadinessEngine(control=V2AuthorityReadinessControl(enabled=True))
    result = engine.evaluate(ready_evidence())
    assert result is not None
    assert result.status is AuthorityReadinessState.HIGH_CONFIDENCE_REVIEW
    assert result.authority is False
    assert all(gate.passed for gate in result.gates)
    assert result.recommendations == ("CONSIDER_FUTURE_MIGRATION_REVIEW",)


def test_soft_failure_is_ready_for_review_not_approval() -> None:
    evidence = replace(ready_evidence(), completed_long_windows=2)
    result = V2AuthorityReadinessEngine(control=V2AuthorityReadinessControl(enabled=True)).evaluate(evidence)
    assert result.status is AuthorityReadinessState.READY_FOR_HUMAN_REVIEW


def test_multiple_soft_failures_are_not_ready() -> None:
    evidence = replace(
        ready_evidence(),
        completed_long_windows=1,
        shadow_match_rate=0.95,
    )
    result = V2AuthorityReadinessEngine(control=V2AuthorityReadinessControl(enabled=True)).evaluate(evidence)
    assert result.status is AuthorityReadinessState.INSUFFICIENT_EVIDENCE
