import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from sentinel.core.router_types import ProviderSpec, RouterDecision, TaskType
from sentinel.providers.provider_manager import ProviderManager


class FakeStream:
    def __init__(self, contents):
        self._contents = contents

    class FakeChunk:
        def __init__(self, content):
            self.choices = [type("Choice", (), {"delta": type("Delta", (), {"content": content, "reasoning_content": ""})()})]

    def __iter__(self):
        for c in self._contents:
            yield self.FakeChunk(c)


class FakeClient:
    def __init__(self, stream=None):
        self.chat = type(
            "Chat",
            (),
            {"completions": type("Completions", (), {"create": staticmethod(lambda **kwargs: stream)})()},
        )()


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
        provider_id="test_provider",
        model="test-model",
        task_type=TaskType.QUICK,
        strategy="priority",
        reason="test",
    )


@pytest.mark.benchmark
class TestProviderClientBenchmarks:
    def test_first_client_acquisition(self, benchmark):
        def _cold():
            pm = ProviderManager()
            pm.set_api_key("test_provider", "test-key")
            return pm._resolve_llm_client("test_provider")
        result = benchmark(_cold)
        # Ensure the call actually built an OpenAI client (not a string or None)
        assert result is not None

    def test_reused_client_acquisition(self, benchmark):
        pm = ProviderManager()
        pm.set_api_key("test_provider", "test-key")
        first = pm._resolve_llm_client("test_provider")

        def _warm():
            return pm._resolve_llm_client("test_provider")

        result = benchmark(_warm)
        assert result is first

    def test_client_close(self, benchmark):
        pm = ProviderManager()
        pm.set_api_key("test_provider", "test-key")
        pm._resolve_llm_client("test_provider")

        def _close():
            pm.close()

        benchmark(_close)
        assert len(pm._clients) == 0


@pytest.mark.benchmark
class TestProviderStreamBenchmarks:
    def test_stream_forwarding_overhead(self, benchmark, provider, decision):
        pm = ProviderManager()
        pm._resolve_llm_client = lambda *_a, **_k: FakeClient(stream=FakeStream(["word"] * 20))

        def _consume():
            return list(pm.call_provider_stream(decision, provider, [{"role": "user", "content": "hi"}]))

        events = benchmark(_consume)
        assert any(e["type"] == "done" for e in events)
