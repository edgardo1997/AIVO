import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from sentinel.core.provider_performance import ProviderPerformanceStore
from sentinel.core.router_types import ProviderSpec, RouterDecision, TaskType
from sentinel.providers.provider_manager import ProviderManager


class FakeDelta:
    def __init__(self, content=None, reasoning_content=None):
        self.content = content
        self.reasoning_content = reasoning_content


class FakeChoice:
    def __init__(self, delta):
        self.delta = delta


class FakeChunk:
    def __init__(self, content=None):
        self.choices = [FakeChoice(FakeDelta(content=content))] if content is not None else []


class FakeStream:
    def __init__(self, contents, fail_at=None, fail_type=None, chunk_delay=0.0):
        self._contents = contents
        self._fail_at = fail_at
        self._fail_type = fail_type
        self._chunk_delay = chunk_delay

    def __iter__(self):
        for i, c in enumerate(self._contents):
            if self._chunk_delay:
                time.sleep(self._chunk_delay)
            if self._fail_at == i:
                if self._fail_type == "timeout":
                    raise TimeoutError("simulated")
                raise RuntimeError("simulated failure")
            if c is None:
                # simulate status-only chunk
                yield FakeChunk()
            else:
                yield FakeChunk(c)


class FakeCompletion:
    def __init__(self, stream=None, response=None):
        self._stream = stream
        self._response = response

    def create(self, **kwargs):
        if self._stream is not None:
            return self._stream
        return self._response


class FailingClient:
    def __init__(self, exc=RuntimeError("simulated")):
        self._exc = exc

    @property
    def chat(self):
        raise self._exc


class FakeClient:
    def __init__(self, stream=None, response=None):
        self.chat = type("Chat", (), {"completions": FakeCompletion(stream=stream, response=response)})()


@pytest.fixture
def provider():
    return ProviderSpec(
        id="test_provider",
        name="Test",
        task_types=[TaskType.QUICK],
        requires_key=False,
        is_local=True,
        default_model="test-model",
        priority=10,
    )


@pytest.fixture
def decision():
    return RouterDecision(
        provider_id="test_provider", model="test-model", task_type=TaskType.QUICK,
        strategy="priority", reason="test",
    )


class TestProviderManagerPerformanceRecording:
    def test_no_record_when_store_not_set(self, provider, decision):
        pm = ProviderManager()
        response = type("R", (), {
            "choices": [type("C", (), {"message": type("M", (), {"content": "hello", "tool_calls": None})()})],
            "usage": type("U", (), {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5})(),
        })()
        pm._resolve_llm_client = lambda *_a, **_k: FakeClient(response=response)
        pm.call_provider(decision, provider, [{"role": "user", "content": "hi"}])

    def test_call_provider_records_success(self, provider, decision):
        store = ProviderPerformanceStore()
        pm = ProviderManager()
        pm.set_performance_store(store)
        response = type("R", (), {
            "choices": [type("C", (), {"message": type("M", (), {"content": "hello", "tool_calls": None})()})],
            "usage": type("U", (), {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5})(),
        })()
        pm._resolve_llm_client = lambda *_a, **_k: FakeClient(response=response)
        pm.call_provider(decision, provider, [{"role": "user", "content": "hi"}])
        agg = store.get_aggregate("test_provider", "test-model")
        assert agg.sample_count == 1
        assert agg.failure_rate == 0.0

    def test_call_provider_records_failure(self, provider, decision):
        store = ProviderPerformanceStore()
        pm = ProviderManager()
        pm.set_performance_store(store)
        pm._resolve_llm_client = lambda *_a, **_k: FailingClient()
        with pytest.raises(RuntimeError):
            pm.call_provider(decision, provider, [{"role": "user", "content": "hi"}])
        agg = store.get_aggregate("test_provider", "test-model")
        assert agg.sample_count == 1
        assert agg.failure_rate == 1.0

    def test_stream_records_success_and_ttft(self, provider, decision):
        store = ProviderPerformanceStore()
        pm = ProviderManager()
        pm.set_performance_store(store)
        pm._resolve_llm_client = lambda *_a, **_k: FakeClient(stream=FakeStream(["Hel", "lo"]))
        result = list(pm.call_provider_stream(decision, provider, [{"role": "user", "content": "hi"}]))
        assert result[-1]["type"] == "done"
        agg = store.get_aggregate("test_provider", "test-model")
        assert agg.sample_count == 1
        assert agg.median_ttft_ms is not None
        # generation speed excludes TTFT; with zero post-first-token time it stays 0.0 and does not divide by zero
        assert agg.median_generation_speed is None

    def test_stream_records_zero_token_response_safely(self, provider, decision):
        store = ProviderPerformanceStore()
        pm = ProviderManager()
        pm.set_performance_store(store)
        pm._resolve_llm_client = lambda *_a, **_k: FakeClient(stream=FakeStream([None, ""]))
        with pytest.raises(RuntimeError):
            list(pm.call_provider_stream(decision, provider, [{"role": "user", "content": "hi"}]))
        # Empty visible content is recorded as a failure, not a success, and does not divide by zero
        agg = store.get_aggregate("test_provider", "test-model")
        assert agg.sample_count == 1
        assert agg.failure_rate == 1.0
        assert agg.median_generation_speed is None

    def test_stream_records_timeout(self, provider, decision):
        store = ProviderPerformanceStore()
        pm = ProviderManager()
        pm.set_performance_store(store)
        pm._resolve_llm_client = lambda *_a, **_k: FakeClient(stream=FakeStream(["x"], fail_at=0, fail_type="timeout"))
        with pytest.raises(TimeoutError):
            list(pm.call_provider_stream(decision, provider, [{"role": "user", "content": "hi"}]))
        agg = store.get_aggregate("test_provider", "test-model")
        assert agg.sample_count == 1
        assert agg.timeout_rate == 1.0

    def test_cancellation_not_counted_as_failure(self, provider, decision):
        store = ProviderPerformanceStore()
        pm = ProviderManager()
        pm.set_performance_store(store)
        e = type("CancelledError", (BaseException,), {})()
        pm._record("test_provider", "test-model", success=False, cancelled=True, error=e)
        agg = store.get_aggregate("test_provider", "test-model")
        assert agg.failure_rate == 0.0
        obs = list(store._observations[("test_provider", "test-model")])[0]
        assert obs.cancelled is True

    def test_no_observation_for_selected_but_uncalled_provider(self, provider, decision):
        store = ProviderPerformanceStore()
        pm = ProviderManager()
        pm.set_performance_store(store)
        # Selecting a provider and deciding not to call it leaves no record
        agg = store.get_aggregate(provider.id, decision.model)
        assert agg.sample_count == 0


class TestProviderManagerClientLifecycle:
    def test_client_is_reused_and_closed(self):
        pm = ProviderManager()
        pm.set_api_key("test_provider", "test-key")
        client1 = pm._resolve_llm_client("test_provider")
        client2 = pm._resolve_llm_client("test_provider")
        assert client1 is client2
        assert "test_provider" in pm._clients
        pm.close()
        assert "test_provider" not in pm._clients
        assert len(pm._clients) == 0

    def test_api_key_change_drops_cached_client(self):
        pm = ProviderManager()
        pm.set_api_key("test_provider", "first-key")
        client1 = pm._resolve_llm_client("test_provider")
        pm.set_api_key("test_provider", "second-key")
        client2 = pm._resolve_llm_client("test_provider")
        assert client1 is not client2

    def test_delete_api_key_closes_client(self):
        pm = ProviderManager()
        pm.set_api_key("test_provider", "test-key")
        pm._resolve_llm_client("test_provider")
        assert "test_provider" in pm._clients
        pm.delete_api_key("test_provider")
        assert "test_provider" not in pm._clients
