from datetime import datetime, timedelta, timezone

from sentinel.decision_long_term_evaluation import (
    DECISION_LONG_TERM_ENABLED,
    DecisionLongTermControl,
    EvaluationWindowState,
    LongTermEvaluationEngine,
)
from sentinel.decision_shadow_validation import DecisionClassification


def test_disabled_by_default_collects_nothing() -> None:
    assert DECISION_LONG_TERM_ENABLED is False
    engine = LongTermEvaluationEngine(DecisionLongTermControl(environ={}))
    assert engine.create() is None
    assert not engine.collect(
        classification=DecisionClassification.EXPECTED_MATCH,
        latency_ms=1,
    )
    assert engine.metrics.snapshot().total_decisions == 0


def test_window_lifecycle_and_aggregate_collection() -> None:
    engine = LongTermEvaluationEngine(DecisionLongTermControl(enabled=True))
    started = datetime(2026, 7, 24, tzinfo=timezone.utc)
    window = engine.create(started_at=started)
    assert window is not None
    assert window.state is EvaluationWindowState.CREATED
    assert window.authority is False
    assert engine.start().state is EvaluationWindowState.COLLECTING
    assert engine.collect(
        classification=DecisionClassification.EXPECTED_MATCH,
        latency_ms=10,
    )
    assert engine.collect(
        classification=DecisionClassification.SECURITY_IMPROVEMENT,
        latency_ms=20,
    )
    completed = engine.complete(ended_at=started + timedelta(hours=1))
    assert completed.state is EvaluationWindowState.COMPLETED
    assert completed.duration_seconds == 3600
    assert engine.metrics.snapshot().total_decisions == 2


def test_collection_errors_are_isolated_as_loss() -> None:
    engine = LongTermEvaluationEngine(DecisionLongTermControl(enabled=True))
    engine.create()
    engine.start()
    assert not engine.collect(
        classification=DecisionClassification.EXPECTED_MATCH,
        latency_ms="invalid",
    )
    assert engine.metrics.snapshot().lost_records == 1
