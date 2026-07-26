from dataclasses import dataclass
from datetime import datetime, timezone

from sentinel.runtime_replay_validation import (
    ReplayComparisonStatus,
    ReplayDatasetV1,
    ReplayValidationControl,
    RuntimeReplayRunner,
)


@dataclass(frozen=True)
class Result:
    shadow_status: str = "OBSERVED"
    differences: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()


class StablePipeline:
    def observe(self, event, *, legacy_status, legacy_comparison):
        return Result()


class AlternatingPipeline:
    calls = 0

    def observe(self, event, *, legacy_status, legacy_comparison):
        self.calls += 1
        return Result(differences=() if self.calls % 2 else ("POLICY_DIVERGENCE",))


def dataset() -> ReplayDatasetV1:
    return ReplayDatasetV1(
        event_id="determinism_event",
        event_type="runtime_shadow",
        version="1.0",
        sanitized_payload_hash="b" * 64,
        timestamp=datetime.now(timezone.utc),
    )


def test_same_input_produces_same_result() -> None:
    runner = RuntimeReplayRunner(
        control=ReplayValidationControl(enabled=True),
        controlled_pipeline=StablePipeline(),
    )
    results = runner.replay(dataset(), repetitions=10)
    assert {item.comparison_result for item in results} == {ReplayComparisonStatus.MATCH}


def test_non_determinism_is_detected() -> None:
    runner = RuntimeReplayRunner(
        control=ReplayValidationControl(enabled=True),
        controlled_pipeline=AlternatingPipeline(),
    )
    results = runner.replay(dataset(), repetitions=4)
    assert results[1].comparison_result is (ReplayComparisonStatus.NON_DETERMINISTIC)
    assert results[3].comparison_result is (ReplayComparisonStatus.NON_DETERMINISTIC)
