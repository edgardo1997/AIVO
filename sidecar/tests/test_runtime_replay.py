from dataclasses import dataclass
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from sentinel.runtime_replay_validation import (
    ReplayDatasetV1,
    ReplayValidationControl,
    ReplayValidationReport,
    RuntimeReplayRunner,
)


@dataclass(frozen=True)
class ShadowResult:
    shadow_status: str = "OBSERVED"
    differences: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    authority: bool = False


class Pipeline:
    def __init__(self) -> None:
        self.events = []

    def observe(self, event, *, legacy_status, legacy_comparison):
        self.events.append(event)
        assert legacy_status == "OBSERVED"
        assert legacy_comparison
        return ShadowResult()


def dataset() -> ReplayDatasetV1:
    return ReplayDatasetV1(
        event_id="event_001",
        event_type="policy_evaluated",
        version="1.0",
        sanitized_payload_hash="a" * 64,
        timestamp=datetime.now(timezone.utc),
    )


def test_dataset_valid_and_rejects_payload() -> None:
    item = dataset()
    assert item.timestamp.utcoffset() is not None
    with pytest.raises(ValidationError):
        ReplayDatasetV1(**item.model_dump(), payload={"prompt": "secret"})


def test_basic_replay_returns_diagnostics_without_authority() -> None:
    pipeline = Pipeline()
    runner = RuntimeReplayRunner(
        control=ReplayValidationControl(enabled=True),
        controlled_pipeline=pipeline,
    )
    results = runner.replay(dataset(), repetitions=3)

    assert len(results) == 3
    assert all(result.authority is False for result in results)
    assert set(pipeline.events[0]) == {
        "event_id",
        "event_type",
        "version",
        "sanitized_payload_hash",
        "timestamp",
    }


def test_disabled_replay_is_noop() -> None:
    pipeline = Pipeline()
    runner = RuntimeReplayRunner(
        control=ReplayValidationControl(enabled=False),
        controlled_pipeline=pipeline,
    )
    assert runner.replay(dataset()) == ()
    assert pipeline.events == []


def test_report_is_human_readable() -> None:
    runner = RuntimeReplayRunner(
        control=ReplayValidationControl(enabled=True),
        controlled_pipeline=Pipeline(),
    )
    results = runner.replay(dataset(), repetitions=2)
    report = ReplayValidationReport.build(
        dataset(),
        results,
        runner.metrics.snapshot(),
    )
    assert report.human_readable().startswith("SENTINEL RUNTIME REPLAY VALIDATION REPORT")


def test_shadow_failure_is_isolated_and_redacted() -> None:
    class FailingPipeline:
        def observe(self, event, *, legacy_status, legacy_comparison):
            raise RuntimeError("secret detail")

    runner = RuntimeReplayRunner(
        control=ReplayValidationControl(enabled=True),
        controlled_pipeline=FailingPipeline(),
    )
    result = runner.replay(dataset())[0]
    assert result.shadow_status == "ERROR"
    assert result.errors == ("shadow_pipeline_failure",)
    assert "secret detail" not in result.model_dump_json()
