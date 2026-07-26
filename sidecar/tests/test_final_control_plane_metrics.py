from sentinel.final_control_plane_readiness import (
    FinalReadinessMetrics,
    FinalReadinessReport,
    FinalReadinessStatus,
)
from sentinel.final_control_plane_readiness.decision import (
    FinalReadinessDecision,
)


def test_metrics_are_aggregate_only() -> None:
    metrics = FinalReadinessMetrics()
    metrics.record(
        status=FinalReadinessStatus.BLOCKED,
        failed_gates=2,
    )
    metrics.record(
        status=FinalReadinessStatus.READY_FOR_HUMAN_REVIEW,
        failed_gates=0,
    )
    snapshot = metrics.snapshot()
    assert snapshot.total_evaluations == 2
    assert snapshot.blocked_count == 1
    assert snapshot.review_count == 1
    assert snapshot.failed_gate_count == 2
    assert not hasattr(metrics, "signals")
    assert not hasattr(metrics, "payloads")


def test_human_report_uses_plain_language() -> None:
    decision = FinalReadinessDecision(
        status=FinalReadinessStatus.READY_FOR_HUMAN_REVIEW,
        confidence=90,
        passed_gates=("SAFETY", "EVIDENCE"),
        failed_gates=(),
        warnings=(),
        evidence_hash="a" * 64,
        correlation_id="final-readiness:test",
    )
    report = FinalReadinessReport(
        decision=decision,
        remaining_risks=("HUMAN_REVIEW_REQUIRED",),
        recommendation="Mantener Legacy y solicitar revisión humana.",
    )
    rendered = report.human_readable()
    assert rendered.startswith("SENTINEL FINAL CONTROL PLANE READINESS REPORT")
    assert "Mantener Legacy" in rendered
