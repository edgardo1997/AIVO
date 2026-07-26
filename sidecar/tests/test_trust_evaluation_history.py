import pytest
from pydantic import ValidationError

from sentinel.v2_trust_evaluation import (
    HistoricalEvidenceV1,
    HistorySummary,
)


def values():
    return {
        "window_count": 2,
        "total_events": 100,
        "stable_windows": 2,
        "equivalence_rate": 0.99,
        "integrity_rate": 1,
        "healthy_window_rate": 1,
        "error_rate": 0.01,
        "divergence_rate": 0.01,
        "critical_divergences": 0,
        "incident_count": 0,
        "rollback_count": 0,
    }


def test_history_summary_returns_independent_immutable_copy() -> None:
    original = HistoricalEvidenceV1(**values())
    summary = HistorySummary().summarize(original)
    assert summary == original
    assert summary is not original


def test_history_rejects_invalid_counts_and_sensitive_fields() -> None:
    with pytest.raises(ValidationError):
        HistoricalEvidenceV1(**{**values(), "stable_windows": 3})
    for field in ("user", "prompt", "command", "path", "secret", "payload"):
        with pytest.raises(ValidationError):
            HistoricalEvidenceV1(**values(), **{field: "sensitive"})
