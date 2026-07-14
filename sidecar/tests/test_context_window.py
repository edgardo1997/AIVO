import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from sentinel.core.context_window import (
    count_tokens,
    count_messages_tokens,
    get_model_window,
    trim_messages,
    should_summarize,
    build_summary_message,
    ContextWindowManager,
    MODEL_CONTEXT_WINDOWS,
    MODEL_FAMILY_DEFAULTS,
)


class TestTokenCounting:
    def test_count_tokens_empty(self):
        assert count_tokens("") == 0

    def test_count_tokens_short(self):
        n = count_tokens("hello world")
        assert n > 0

    def test_count_tokens_longer(self):
        short = count_tokens("x" * 100)
        long = count_tokens("x" * 200)
        assert long > short

    def test_count_messages_tokens_structure(self):
        msgs = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello"},
        ]
        info = count_messages_tokens(msgs)
        assert "total_tokens" in info
        assert "messages" in info
        assert info["message_count"] == 2
        assert info["total_tokens"] > 0

    def test_count_messages_tokens_empty(self):
        info = count_messages_tokens([])
        assert info["total_tokens"] == 2
        assert info["message_count"] == 0


class TestModelWindow:
    def test_get_model_window_known(self):
        assert get_model_window("gpt-4o") == 128000
        assert get_model_window("claude-sonnet-4") == 200000

    def test_get_model_window_family(self):
        assert get_model_window("gpt-3.5-turbo") == 16384
        assert get_model_window("gpt-4-turbo") == 128000

    def test_get_model_window_default(self):
        assert get_model_window(None) == 8192
        assert get_model_window("unknown-model") == 8192


class TestTrimMessages:
    def test_trim_noop_when_under_budget(self):
        msgs = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hi"},
        ]
        trimmed = trim_messages(msgs, max_tokens=100000)
        assert len(trimmed) == 2

    def test_trim_preserves_system(self):
        msgs = [{"role": "system", "content": "sys"}] + [{"role": "user", "content": "x" * 100} for _ in range(20)]
        trimmed = trim_messages(msgs, max_tokens=200)
        assert len([m for m in trimmed if m.get("role") == "system"]) == 1

    def test_trim_keeps_recent(self):
        msgs = [{"role": "user", "content": f"msg {i} " + "x" * 50} for i in range(20)]
        trimmed = trim_messages(msgs, max_tokens=200)
        assert len(trimmed) < len(msgs)
        assert trimmed[-1]["content"].startswith("msg 19")

    def test_trim_empty(self):
        assert trim_messages([], 1000) == []


class TestSummarize:
    def test_should_summarize_below_threshold(self):
        msgs = [{"role": "user", "content": "hi"}]
        assert should_summarize(msgs, max_tokens=100000) is False

    def test_should_summarize_above_threshold(self):
        long = [{"role": "user", "content": "x" * 5000}]
        assert should_summarize(long, max_tokens=100) is True

    def test_build_summary_message(self):
        msgs = [
            {"role": "user", "content": "What is the weather?"},
            {"role": "assistant", "content": "It is sunny."},
        ]
        sm = build_summary_message(msgs)
        assert sm["role"] == "system"
        assert "weather" in sm["content"]
        assert "sunny" in sm["content"]

    def test_build_summary_empty(self):
        sm = build_summary_message([])
        assert sm["role"] == "system"
        assert sm["content"] == ""


class TestContextWindowManager:
    def test_default_window(self):
        mgr = ContextWindowManager()
        assert mgr.get_window("unknown") == 8192
        assert mgr.get_window("gpt-4o") == 128000

    def test_set_model_window(self):
        mgr = ContextWindowManager()
        mgr.set_model_window("custom", 16000)
        assert mgr.get_window("custom") == 16000

    def test_manage_noop_for_small(self):
        mgr = ContextWindowManager()
        msgs = [{"role": "user", "content": "hi"}]
        result = mgr.manage(msgs, model="gpt-4o")
        assert result["messages"] == msgs
        assert result["trimmed"] == 0
        assert result["summarized"] is False

    def test_manage_trims_when_over(self):
        mgr = ContextWindowManager(default_window=200)
        msgs = [{"role": "user", "content": f"long message {i} " + "x" * 200} for i in range(10)]
        result = mgr.manage(msgs, max_tokens=200)
        assert result["messages"] != msgs
        assert len(result["messages"]) < len(msgs)

    def test_manage_summarizes_long_history(self):
        mgr = ContextWindowManager(default_window=200, summarization_threshold=0.1)
        msgs = [{"role": "system", "content": "You are helpful."}] + [
            {"role": "user", "content": f"msg {i}"} for i in range(20)
        ]
        result = mgr.manage(msgs, max_tokens=200)
        # Should summarize since 20 user msgs exceed threshold
        assert result["final_count"] < len(msgs)

    def test_manage_force_summarize(self):
        mgr = ContextWindowManager()
        msgs = [{"role": "user", "content": f"msg {i}"} for i in range(10)]
        result = mgr.manage(msgs, max_tokens=999999, force_summarize=True)
        assert result["summarized"] is True

    def test_manage_empty(self):
        mgr = ContextWindowManager()
        result = mgr.manage([], model="gpt-4o")
        assert result["messages"] == []
        assert result["final_count"] == 0

    def test_manage_returns_metadata(self):
        mgr = ContextWindowManager()
        msgs = [{"role": "user", "content": "hello"}]
        result = mgr.manage(msgs, model="gpt-4o")
        assert "original_count" in result
        assert "final_count" in result
        assert "trimmed" in result
        assert "summarized" in result
        assert "total_tokens" in result

    def test_manage_preserves_system_prompt(self):
        mgr = ContextWindowManager(default_window=30)
        msgs = [
            {"role": "system", "content": "IMPORTANT: You are Sentinel."},
            {"role": "user", "content": "x" * 200},
            {"role": "assistant", "content": "y" * 200},
        ]
        result = mgr.manage(msgs, max_tokens=40)
        sys_msgs = [m for m in result["messages"] if m.get("role") == "system"]
        assert len(sys_msgs) >= 1
        assert "IMPORTANT" in sys_msgs[0]["content"]


class TestContextWindowAPI:
    def setup_method(self):
        from modules.sentinel_bridge import reset_bridge

        reset_bridge()

    def test_chat_still_works(self):
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        resp = client.post("/api/sentinel/chat", json={"message": "hello"})
        assert resp.status_code == 200
        data = resp.json()
        assert "response" in data
        assert "pipeline" in data
