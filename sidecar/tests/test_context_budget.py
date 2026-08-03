import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sentinel.core.context_budget import (
    ContextBudgetManager,
    DEFAULT_CONTEXT_WINDOWS,
    RequestPurpose,
)


class TestContextBudgetManager:
    def test_conversation_fits_small_history(self):
        mgr = ContextBudgetManager()
        budget = mgr.budget_for("gpt-4o", purpose=RequestPurpose.CONVERSATION, num_history_messages=10)
        assert budget.max_input_tokens > 0
        assert budget.available_for_messages > 0
        assert budget.reserve_history == 10 * 64

    def test_governed_action_gets_larger_ratio(self):
        mgr = ContextBudgetManager()
        conv = mgr.budget_for("gpt-4o", purpose=RequestPurpose.CONVERSATION)
        gov = mgr.budget_for("gpt-4o", purpose=RequestPurpose.GOVERNED_ACTION)
        assert gov.max_input_tokens > conv.max_input_tokens

    def test_local_model_has_smaller_window(self):
        mgr = ContextBudgetManager()
        budget = mgr.budget_for("Qwen3-1.7B-Q8_0.gguf")
        assert budget.max_input_tokens <= DEFAULT_CONTEXT_WINDOWS["Qwen3-1.7B-Q8_0.gguf"]

    def test_truncate_keeps_system_and_recent_messages(self):
        mgr = ContextBudgetManager()
        # Budget with very small window so only system + a couple messages fit
        budget = mgr.budget_for(
            "Qwen3-1.7B-Q8_0.gguf",
            purpose=RequestPurpose.CONVERSATION,
            extra_overhead=2200,  # artificially tight for the corrected 4096-token local window
        )
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Message 1 " * 100},
            {"role": "assistant", "content": "Reply 1 " * 100},
            {"role": "user", "content": "Message 2 " * 100},
            {"role": "assistant", "content": "Reply 2 " * 100},
            {"role": "user", "content": "Current question?"},
        ]
        result = mgr.truncate(messages, budget)
        assert result[0]["role"] == "system"
        assert result[-1]["content"] == "Current question?"
        assert len(result) < len(messages)

    def test_manage_reports_dropped_and_estimated_tokens(self):
        mgr = ContextBudgetManager()
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hola " * 200},
        ]
        result = mgr.manage(messages, "Qwen3-1.7B-Q8_0.gguf")
        assert "budget" in result
        assert "messages" in result
        assert "dropped" in result
        assert "estimated_tokens" in result
