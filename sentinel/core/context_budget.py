"""Context budget management.

One authoritative owner for how much context a request can consume,
broken down by core instructions, history, tool definitions, memory
and provider-specific overhead.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class RequestPurpose(Enum):
    CONVERSATION = "conversation"
    TECHNICAL = "technical"
    REASONING = "reasoning"
    GOVERNED_ACTION = "governed_action"


DEFAULT_CONTEXT_WINDOWS: Dict[str, int] = {
    "gpt-4o": 128000,
    "gpt-4o-mini": 128000,
    "Qwen3-1.7B-Q8_0.gguf": 4096,
    "llama3": 8192,
    "deepseek/deepseek-v4-flash:free": 64000,
    "nvidia/nemotron-3-super-120b-a12b": 128000,
}


@dataclass
class ContextBudget:
    """Budget allocation in tokens."""

    max_input_tokens: int
    reserve_system: int = 0
    reserve_history: int = 0
    reserve_memory: int = 0
    reserve_tools: int = 0
    reserve_overhead: int = 0
    reserved: int = field(init=False)
    available_for_messages: int = field(init=False)

    def __post_init__(self):
        self.reserved = (
            self.reserve_system
            + self.reserve_history
            + self.reserve_memory
            + self.reserve_tools
            + self.reserve_overhead
        )
        self.available_for_messages = max(0, self.max_input_tokens - self.reserved)

    def fits(self, estimated_tokens: int) -> bool:
        return estimated_tokens <= self.available_for_messages

    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_input_tokens": self.max_input_tokens,
            "reserve_system": self.reserve_system,
            "reserve_history": self.reserve_history,
            "reserve_memory": self.reserve_memory,
            "reserve_tools": self.reserve_tools,
            "reserve_overhead": self.reserve_overhead,
            "reserved": self.reserved,
            "available_for_messages": self.available_for_messages,
        }


def _estimate_tokens(text: str) -> int:
    """Very rough token estimate; provider-specific counters should refine."""
    return max(1, len(text) // 4)


def _sum_messages(messages: List[Dict[str, Any]]) -> int:
    return sum(_estimate_tokens(str(m.get("content", ""))) for m in messages)


class ContextBudgetManager:
    """Compute and enforce per-request context budgets."""

    def __init__(
        self,
        context_windows: Optional[Dict[str, int]] = None,
        purpose_ratios: Optional[Dict[RequestPurpose, float]] = None,
    ):
        self._context_windows = context_windows or DEFAULT_CONTEXT_WINDOWS
        self._purpose_ratios = purpose_ratios or {
            RequestPurpose.CONVERSATION: 0.75,
            RequestPurpose.TECHNICAL: 0.65,
            RequestPurpose.REASONING: 0.65,
            RequestPurpose.GOVERNED_ACTION: 0.80,
        }
        self._default_overhead = 128

    def budget_for(
        self,
        model: str,
        purpose: RequestPurpose = RequestPurpose.CONVERSATION,
        num_history_messages: int = 0,
        num_memories: int = 0,
        num_tools: int = 0,
        extra_overhead: int = 0,
    ) -> ContextBudget:
        """Return a budget for a request given the model and use case."""
        total = self._context_windows.get(model, 128000)
        usable = int(total * self._purpose_ratios.get(purpose, 0.75))

        # Base reservation for the system prompt + generation headroom
        reserve_system = 256
        reserve_history = num_history_messages * 64
        reserve_memory = num_memories * 128
        reserve_tools = num_tools * 64

        return ContextBudget(
            max_input_tokens=usable,
            reserve_system=reserve_system,
            reserve_history=reserve_history,
            reserve_memory=reserve_memory,
            reserve_tools=reserve_tools,
            reserve_overhead=self._default_overhead + extra_overhead,
        )

    def truncate(
        self,
        messages: List[Dict[str, Any]],
        budget: ContextBudget,
        keep_system_first: bool = True,
    ) -> List[Dict[str, Any]]:
        """Truncate messages to fit within the budget, preserving order."""
        if not messages:
            return []

        system_messages = [m for m in messages if keep_system_first and m.get("role") == "system"]
        other_messages = [m for m in messages if m not in system_messages]

        # Reserve the system messages first
        used = _sum_messages(system_messages)
        remaining = budget.available_for_messages - used
        kept: List[Dict[str, Any]] = list(system_messages)

        # Keep the most recent messages that still fit
        for msg in reversed(other_messages):
            cost = _estimate_tokens(str(msg.get("content", "")))
            if cost <= remaining:
                kept.append(msg)
                remaining -= cost
            else:
                break

        # Reverse back to original order
        tail = [m for m in kept if m.get("role") != "system"]
        tail.reverse()
        return system_messages + tail

    def manage(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        purpose: RequestPurpose = RequestPurpose.CONVERSATION,
        **budget_kwargs: Any,
    ) -> Dict[str, Any]:
        """Compute budget and truncate messages in one call."""
        budget = self.budget_for(model, purpose, **budget_kwargs)
        truncated = self.truncate(messages, budget)
        return {
            "budget": budget.to_dict(),
            "messages": truncated,
            "dropped": len(messages) - len(truncated),
            "estimated_tokens": _sum_messages(truncated),
        }
