import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from sentinel.core.router_types import ProviderSpec, RouterDecision, TaskType
from sentinel.providers.provider_manager import ProviderManager
from sentinel.core.model_router import ModelRouter
from sentinel.core.provider_performance import ProviderPerformanceStore


class FakeDB:
    def __init__(self):
        self.messages = []

    def append_conversation_message(self, user_id, session_id, title, message, updated_at):
        self.messages.append({
            "user_id": user_id,
            "session_id": session_id,
            "title": title,
            "message": message,
            "updated_at": updated_at,
        })
        return {}


class FailingDB(FakeDB):
    def append_conversation_message(self, *args, **kwargs):
        raise RuntimeError("database unavailable")


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


class TestProviderClientLifecycle:
    def test_client_invalidated_when_base_url_changes(self, monkeypatch, provider, decision):
        pm = ProviderManager()
        pm.set_api_key("test_provider", "test-key")
        client1 = pm._resolve_llm_client("test_provider")
        monkeypatch.setitem(
            __import__("sentinel.providers.provider_manager", fromlist=["PROVIDER_URLS"]).PROVIDER_URLS,
            "test_provider",
            "http://new-base/v1",
        )
        client2 = pm._resolve_llm_client("test_provider")
        assert client1 is not client2

    def test_model_router_close_closes_provider_manager_clients(self, monkeypatch):
        # Speed up router construction by reducing providers if necessary; we only care about lifecycle.
        mr = ModelRouter()
        mr._provider_manager.set_api_key("test_provider", "test-key")
        mr._provider_manager._resolve_llm_client("test_provider")
        assert "test_provider" in mr._provider_manager._clients
        mr.close()
        assert len(mr._provider_manager._clients) == 0

    def test_credentials_isolated_by_provider(self):
        pm = ProviderManager()
        pm.set_api_key("provider_a", "key-a")
        pm.set_api_key("provider_b", "key-b")
        a = pm._resolve_llm_client("provider_a")
        b = pm._resolve_llm_client("provider_b")
        assert a is not b


class TestStreamInvariants:
    class FakeChunk:
        def __init__(self, content="", reasoning_content=""):
            self.choices = [type("Choice", (), {"delta": type("Delta", (), {"content": content, "reasoning_content": reasoning_content})()})]

    class FakeStream:
        def __init__(self, contents):
            self._contents = contents

        def __iter__(self):
            for c in self._contents:
                yield TestStreamInvariants.FakeChunk(c)

    class FakeClient:
        def __init__(self, stream=None):
            self.chat = type(
                "Chat",
                (),
                {"completions": type("Completions", (), {"create": staticmethod(lambda **kwargs: stream)})()},
            )()

    def test_unicode_chunks_preserved(self, provider, decision):
        pm = ProviderManager()
        pm._resolve_llm_client = lambda *_a, **_k: TestStreamInvariants.FakeClient(
            stream=TestStreamInvariants.FakeStream(["héllo", "🙂"])
        )
        result = list(pm.call_provider_stream(decision, provider, [{"role": "user", "content": "hi"}]))
        deltas = [r["content"] for r in result if r["type"] == "delta"]
        assert "".join(deltas) == "héllo🙂"

    def test_no_duplicate_delta_chunks(self, provider, decision):
        pm = ProviderManager()
        pm._resolve_llm_client = lambda *_a, **_k: TestStreamInvariants.FakeClient(
            stream=TestStreamInvariants.FakeStream(["a", "b", "c"])
        )
        result = list(pm.call_provider_stream(decision, provider, [{"role": "user", "content": "hi"}]))
        deltas = [r["content"] for r in result if r["type"] == "delta"]
        assert deltas == ["a", "b", "c"]


class TestPersistence:
    def test_persisted_turn_contains_prompt_and_response(self, monkeypatch):
        fake_db = FakeDB()
        monkeypatch.setattr(
            "sidecar.modules.sentinel_bridge_helpers._conversation_db",
            lambda: fake_db,
        )
        from sidecar.modules.sentinel_bridge_helpers import _persist_conversation_turn

        _persist_conversation_turn(
            "user-1",
            "session-1",
            "user prompt",
            "assistant response",
            provider="test_provider",
            model="test-model",
            performance={"ttft_ms": 15.0},
            interrupted=False,
        )
        assert len(fake_db.messages) == 1
        msg = fake_db.messages[0]["message"]
        assert msg["prompt"] == "user prompt"
        assert msg["response"] == "assistant response"
        assert msg["provider"] == "test_provider"
        assert msg["model"] == "test-model"
        assert msg["performance"]["ttft_ms"] == 15.0

    def test_interrupted_turn_is_marked(self, monkeypatch):
        fake_db = FakeDB()
        monkeypatch.setattr(
            "sidecar.modules.sentinel_bridge_helpers._conversation_db",
            lambda: fake_db,
        )
        from sidecar.modules.sentinel_bridge_helpers import _persist_conversation_turn

        _persist_conversation_turn(
            "user-1", "session-1", "prompt", "partial response", interrupted=True
        )
        msg = fake_db.messages[0]["message"]
        assert "interrumpida" in msg["error"]

    def test_persistence_failure_propagates(self, monkeypatch):
        monkeypatch.setattr(
            "sidecar.modules.sentinel_bridge_helpers._conversation_db",
            lambda: FailingDB(),
        )
        from sidecar.modules.sentinel_bridge_helpers import _persist_conversation_turn

        with pytest.raises(RuntimeError, match="database unavailable"):
            _persist_conversation_turn("user-1", "session-1", "prompt", "response")
