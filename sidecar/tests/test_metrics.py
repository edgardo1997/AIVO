"""Normalized metrics store tests."""

import pytest

from sentinel.core.metrics import MetricsStore, RoutingMetric


def test_metric_rejects_prompt():
    store = MetricsStore()
    with pytest.raises(ValueError):
        store.record(RoutingMetric(
            request_id="r1",
            correlation_id="c1",
            provider="prompt",
            model="gpt-4o",
            operation="chat",
            routing_reason="USER_PREFERENCE",
            candidate_count=3,
            latency_ms=123.0,
            time_to_first_token_ms=45.0,
            input_tokens=10,
            output_tokens=20,
            total_tokens=30,
            estimated_cost=0.01,
            reserved_cost=0.01,
            actual_cost=0.012,
            fallback_used=False,
            fallback_reason="",
            status="completed",
            error_code="",
        ))


def test_query_by_correlation_id():
    store = MetricsStore()
    store.record(RoutingMetric(
        request_id="r1",
        correlation_id="c1",
        provider="ollama",
        model="llama3",
        operation="chat",
        routing_reason="LOCAL_PREFERRED",
        candidate_count=2,
        latency_ms=456.0,
        time_to_first_token_ms=None,
        input_tokens=5,
        output_tokens=10,
        total_tokens=15,
        estimated_cost=0.0,
        reserved_cost=0.0,
        actual_cost=0.0,
        fallback_used=False,
        fallback_reason="",
        status="completed",
        error_code="",
    ))
    assert len(store.query(correlation_id="c1")) == 1
    assert len(store.query(correlation_id="c2")) == 0
