from sentinel.v2_authority_readiness import (
    AuthorityReadinessMetrics,
    AuthorityReadinessReport,
    AuthorityReadinessState,
    GateResult,
    ReadinessEvidenceV1,
    V2AuthorityReadinessControl,
    V2AuthorityReadinessEngine,
)


def test_metrics_are_aggregate_only() -> None:
    metrics = AuthorityReadinessMetrics()
    gates = (
        GateResult("CONTRACT", True, (), False),
        GateResult("SECURITY", False, ("IDENTITY_MISSING",), True),
    )
    metrics.record(
        state=AuthorityReadinessState.BLOCKED,
        gates=gates,
        error=True,
    )
    snapshot = metrics.snapshot()
    assert snapshot.validation_runs == 1
    assert snapshot.blocked_runs == 1
    assert snapshot.gates_passed == 1
    assert snapshot.gates_failed == 1
    assert snapshot.errors == 1
    assert not hasattr(metrics, "evidence")
    assert not hasattr(metrics, "payloads")


def test_human_report_is_explicitly_evidence_only() -> None:
    evidence = ReadinessEvidenceV1(
        True,
        True,
        0,
        1.0,
        0,
        0,
        True,
        True,
        False,
        True,
        3,
        0,
        10,
        0,
        False,
        False,
        False,
    )
    engine = V2AuthorityReadinessEngine(control=V2AuthorityReadinessControl(enabled=True))
    result = engine.evaluate(evidence)
    report = AuthorityReadinessReport(
        result=result,
        metrics=engine.metrics.snapshot(),
    )
    rendered = report.human_readable()
    assert rendered.startswith("SENTINEL V2 AUTHORITY READINESS REPORT")
    assert "HIGH_CONFIDENCE_REVIEW" in rendered
    assert "CONSIDER_FUTURE_MIGRATION_REVIEW" in rendered
