import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from sentinel.core.provider_performance import (
    ProviderPerformanceObservation,
    ProviderPerformanceStore,
    _median,
    _percentile,
)
from sentinel.core.router_types import ProviderSpec, TaskType
from sentinel.routing.provider_selector import ProviderSelector


class FakeCapabilityManager:
    def assess(self, model_id, profile, config):
        class _Result:
            def to_dict(self):
                return {"compatible": True, "reason": ""}
        return _Result()


@pytest.fixture
def providers():
    return {
        "fast_cloud": ProviderSpec(
            id="fast_cloud", name="Fast Cloud", task_types=[TaskType.QUICK, TaskType.REASONING],
            requires_key=True, default_model="fast-model", priority=20,
        ),
        "slow_cloud": ProviderSpec(
            id="slow_cloud", name="Slow Cloud", task_types=[TaskType.QUICK, TaskType.REASONING],
            requires_key=True, default_model="slow-model", priority=20,
        ),
        "local": ProviderSpec(
            id="local", name="Local", task_types=[TaskType.QUICK, TaskType.LOCAL],
            requires_key=False, is_local=True, default_model="local-model", priority=50,
        ),
    }


@pytest.fixture
def selector(providers):
    sel = ProviderSelector(providers=providers, capability_manager=FakeCapabilityManager())
    sel.set_api_key("fast_cloud", "key")
    sel.set_api_key("slow_cloud", "key")
    return sel


class TestProviderPerformanceStore:
    def test_empty_store_returns_neutral_score(self):
        store = ProviderPerformanceStore()
        assert store.performance_score("p", "m") == 0.5
        agg = store.get_aggregate("p", "m")
        assert agg.sample_count == 0

    def test_fast_provider_receives_positive_score(self):
        store = ProviderPerformanceStore()
        for _ in range(10):
            store.record(ProviderPerformanceObservation(
                provider_id="fast", model_id="m",
                ttft_ms=100.0, generation_tokens_per_second=80.0, success=True,
            ))
        score = store.performance_score("fast", "m")
        assert score > 0.7

    def test_slow_but_reliable_provider_remains_eligible(self):
        store = ProviderPerformanceStore()
        for _ in range(10):
            store.record(ProviderPerformanceObservation(
                provider_id="slow", model_id="m",
                ttft_ms=4000.0, generation_tokens_per_second=5.0, success=True,
            ))
        score = store.performance_score("slow", "m")
        assert 0.3 < score < 0.7

    def test_unreliable_provider_receives_reliability_penalty(self):
        store = ProviderPerformanceStore()
        for i in range(10):
            store.record(ProviderPerformanceObservation(
                provider_id="flaky", model_id="m",
                ttft_ms=1000.0, generation_tokens_per_second=20.0,
                success=(i % 2 == 0),
            ))
        score = store.performance_score("flaky", "m")
        assert score < 0.7

    def test_repeated_timeouts_recorded(self):
        store = ProviderPerformanceStore()
        for _ in range(5):
            store.record(ProviderPerformanceObservation(
                provider_id="timeout", model_id="m",
                success=False, timeout=True,
            ))
        agg = store.get_aggregate("timeout", "m")
        assert agg.timeout_rate == 1.0
        assert agg.failure_rate == 1.0

    def test_stale_observations_expire(self):
        store = ProviderPerformanceStore(max_age_seconds=0.1)
        store.record(ProviderPerformanceObservation(
            provider_id="stale", model_id="m", timestamp=time.monotonic(),
            ttft_ms=100.0, success=True,
        ))
        assert store.get_aggregate("stale", "m").sample_count == 1
        time.sleep(0.15)
        assert store.get_aggregate("stale", "m").sample_count == 0

    def test_history_bounded_by_count(self):
        store = ProviderPerformanceStore(max_observations=3)
        for i in range(10):
            store.record(ProviderPerformanceObservation(
                provider_id="bounded", model_id="m", timestamp=time.monotonic() + i,
                ttft_ms=float(i), success=True,
            ))
        agg = store.get_aggregate("bounded", "m")
        assert agg.sample_count == 3

    def test_small_sample_cannot_dominate(self):
        store = ProviderPerformanceStore()
        # A single excellent sample should not yield a near-perfect score
        store.record(ProviderPerformanceObservation(
            provider_id="one", model_id="m",
            ttft_ms=1.0, generation_tokens_per_second=100.0, success=True,
        ))
        score = store.performance_score("one", "m")
        assert score < 0.95

    def test_outlier_ttft_does_not_dominate(self):
        store = ProviderPerformanceStore()
        for _ in range(9):
            store.record(ProviderPerformanceObservation(
                provider_id="outlier", model_id="m",
                ttft_ms=100.0, success=True,
            ))
        store.record(ProviderPerformanceObservation(
            provider_id="outlier", model_id="m",
            ttft_ms=50000.0, success=True,
        ))
        agg = store.get_aggregate("outlier", "m")
        assert agg.median_ttft_ms == 100.0

    def test_cold_start_does_not_permanently_poison(self):
        store = ProviderPerformanceStore()
        store.record(ProviderPerformanceObservation(
            provider_id="cold", model_id="m",
            ttft_ms=10000.0, generation_tokens_per_second=1.0, success=True,
        ))
        for _ in range(10):
            store.record(ProviderPerformanceObservation(
                provider_id="cold", model_id="m",
                ttft_ms=100.0, generation_tokens_per_second=60.0, success=True,
            ))
        agg = store.get_aggregate("cold", "m")
        assert agg.median_ttft_ms == 100.0

    def test_no_prompt_or_response_stored(self):
        obs = ProviderPerformanceObservation(
            provider_id="p", model_id="m", success=True,
        )
        d = obs.to_dict()
        assert "prompt" not in d
        assert "response" not in d
        assert "api_key" not in d

    def test_cancellation_recorded_separately(self):
        store = ProviderPerformanceStore()
        store.record(ProviderPerformanceObservation(
            provider_id="cancelled", model_id="m",
            success=False, cancelled=True,
        ))
        agg = store.get_aggregate("cancelled", "m")
        assert agg.sample_count == 1
        assert agg.failure_rate == 0.0
        assert not agg.timeout_rate

    def test_median_percentile_helpers(self):
        assert _median([1, 2, 3, 4]) == 2.5
        assert _median([1, 2, 3]) == 2
        assert _percentile([1, 2, 3, 4, 5], 0.5) == 3


class TestProviderPerformanceRouting:
    def test_healthy_fast_provider_gets_positive_score(self, selector):
        store = ProviderPerformanceStore()
        for _ in range(10):
            store.record(ProviderPerformanceObservation(
                provider_id="fast_cloud", model_id="fast-model",
                ttft_ms=100.0, generation_tokens_per_second=80.0, success=True,
            ))
            store.record(ProviderPerformanceObservation(
                provider_id="slow_cloud", model_id="slow-model",
                ttft_ms=3000.0, generation_tokens_per_second=5.0, success=True,
            ))
        selector.set_performance_store(store)
        decision = selector.select(TaskType.REASONING)
        assert decision.provider_id == "fast_cloud"
        assert decision.selection_trace["resource_score_components"]["fast_cloud"]["performance_fit"] > 0.7
        assert decision.selection_trace["resource_score_components"]["slow_cloud"]["performance_fit"] < 0.7

    def test_same_tier_performance_can_influence_selection(self, selector):
        store = ProviderPerformanceStore()
        for _ in range(10):
            store.record(ProviderPerformanceObservation(
                provider_id="slow_cloud", model_id="slow-model",
                ttft_ms=5000.0, success=False,
            ))
        # fast_cloud has no observations but is neutral; slow_cloud is penalized
        selector.set_performance_store(store)
        decision = selector.select(TaskType.REASONING)
        assert decision.provider_id == "fast_cloud"

    def test_explicit_valid_provider_remains_selected(self, selector):
        store = ProviderPerformanceStore()
        for _ in range(10):
            store.record(ProviderPerformanceObservation(
                provider_id="slow_cloud", model_id="slow-model",
                ttft_ms=100.0, generation_tokens_per_second=80.0, success=True,
            ))
            store.record(ProviderPerformanceObservation(
                provider_id="fast_cloud", model_id="fast-model",
                ttft_ms=5000.0, success=False,
            ))
        selector.set_performance_store(store)
        decision = selector.select(TaskType.REASONING, explicit_provider="fast_cloud")
        assert decision.provider_id == "fast_cloud"

    def test_privacy_forbids_cloud_regardless_of_speed(self, selector):
        store = ProviderPerformanceStore()
        for _ in range(10):
            store.record(ProviderPerformanceObservation(
                provider_id="fast_cloud", model_id="fast-model",
                ttft_ms=1.0, generation_tokens_per_second=100.0, success=True,
            ))
        selector.set_performance_store(store)
        decision = selector.select(TaskType.QUICK, context={"cloud_allowed": False})
        assert selector._providers[decision.provider_id].is_local

    def test_provider_availability_missing_key_excludes_provider(self, selector):
        selector.delete_api_key("slow_cloud")
        decision = selector.select(TaskType.REASONING)
        assert decision.provider_id == "fast_cloud"
