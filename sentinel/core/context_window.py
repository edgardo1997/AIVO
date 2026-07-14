"""
Token-aware context window management for AI conversations.

Handles:
- Token counting (chars/4 heuristic, optional tiktoken)
- Per-model context window limits
- Smart message trimming (preserves system prompt + recent messages)
- Conversation summarization (compress old history into a summary)
- Full pipeline: count, decide, act
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

DEFAULT_RESERVE_TOKENS = 1024

MODEL_CONTEXT_WINDOWS: Dict[str, int] = {
    "gpt-4-turbo": 128000,
    "gpt-4o": 128000,
    "gpt-4o-mini": 128000,
    "gpt-4": 8192,
    "gpt-3.5-turbo": 16384,
    "claude-sonnet-4": 200000,
    "claude-3-haiku": 200000,
    "claude-3-opus": 200000,
    "deepseek-v4-flash": 65536,
    "deepseek-chat": 32768,
    "gemini-2.5-flash": 1048576,
    "gemini-2.5-pro": 1048576,
    "llama-3.3-70b-versatile": 131072,
    "llama3": 8192,
    "llama3.1": 131072,
    "mistral-large-latest": 32768,
    "mistral-medium": 32768,
    "codestral": 32768,
}

MODEL_FAMILY_DEFAULTS: Dict[str, int] = {
    "gpt": 8192,
    "claude": 100000,
    "deepseek": 32768,
    "gemini": 32768,
    "llama": 8192,
    "mistral": 32768,
    "phi": 4096,
    "qwen": 32768,
    "command": 4096,
}


def count_tokens(text: str, model: Optional[str] = None) -> int:
    if not text:
        return 0
    try:
        import tiktoken

        encoding_name = _encoding_for_model(model) if model else "cl100k_base"
        enc = tiktoken.get_encoding(encoding_name)
        return len(enc.encode(text))
    except Exception as exc:
        logger.debug("Falling back to heuristic token counting: %s", exc)
    if model and model.startswith("gpt-4") or (model and "claude" in model):
        return (len(text) + 1) // 3
    return (len(text) + 3) // 4


def _encoding_for_model(model: str) -> str:
    model_lower = model.lower()
    if model_lower.startswith("gpt-4") or model_lower.startswith("gpt-3"):
        return "cl100k_base"
    if "deepseek" in model_lower:
        return "cl100k_base"
    return "cl100k_base"


def get_model_window(model: Optional[str]) -> int:
    if not model:
        return 8192
    if model in MODEL_CONTEXT_WINDOWS:
        return MODEL_CONTEXT_WINDOWS[model]
    for key, window in sorted(MODEL_CONTEXT_WINDOWS.items(), key=lambda x: -len(x[0])):
        if model.lower().startswith(key):
            return window
    for prefix, window in sorted(MODEL_FAMILY_DEFAULTS.items(), key=lambda x: -len(x[0])):
        if model.lower().startswith(prefix):
            return window
    return 8192


def count_messages_tokens(messages: List[Dict[str, str]], model: Optional[str] = None) -> Dict[str, Any]:
    total = 0
    per_msg = []
    for m in messages:
        role_tokens = count_tokens(m.get("role", ""), model=model)
        content_tokens = count_tokens(m.get("content", ""), model=model)
        overhead = 4
        msg_tokens = role_tokens + content_tokens + overhead
        total += msg_tokens
        per_msg.append(
            {
                "role": m.get("role", "unknown"),
                "tokens": msg_tokens,
            }
        )
    total += 2
    return {"total_tokens": total, "messages": per_msg, "message_count": len(messages)}


def trim_messages(
    messages: List[Dict[str, str]],
    max_tokens: int,
    reserve: int = DEFAULT_RESERVE_TOKENS,
) -> List[Dict[str, str]]:
    if not messages:
        return messages

    current = count_messages_tokens(messages).get("total_tokens", 0)
    if current <= max_tokens:
        return messages

    budget = max(max_tokens - reserve, max_tokens // 2)
    if budget <= 0:
        budget = max_tokens

    sys_msgs = [m for m in messages if m.get("role") == "system"]
    non_sys = [m for m in messages if m.get("role") != "system"]

    result = list(sys_msgs)
    for m in reversed(non_sys):
        trial = result + [m]
        total = count_messages_tokens(trial).get("total_tokens", 0)
        if total <= budget:
            result.append(m)
        else:
            break

    result = sys_msgs + list(reversed([m for m in result if m.get("role") != "system"]))
    trimmed_count = len(messages) - len(result)
    if trimmed_count > 0:
        logger.info("Trimmed %d messages to fit %d token budget", trimmed_count, budget)
    return result


def should_summarize(messages: List[Dict[str, str]], max_tokens: int, threshold: float = 0.85) -> bool:
    if not messages or max_tokens <= 0:
        return False
    total = count_messages_tokens(messages).get("total_tokens", 0)
    return total > max_tokens * threshold


def build_summary_message(
    messages: List[Dict[str, str]],
    model: Optional[str] = None,
) -> Dict[str, str]:
    if not messages:
        return {"role": "system", "content": ""}

    lines = []
    for m in messages:
        role = m.get("role", "unknown")
        content = m.get("content", "")
        preview = content[:200].replace("\n", " ")
        lines.append(f"[{role}]: {preview}")

    summary = "Previous conversation summary:\n" + "\n".join(lines) + "\n---"
    summary_tokens = count_tokens(summary, model=model)
    if summary_tokens > 512:
        ratio = 512 / max(summary_tokens, 1)
        char_limit = int(len(summary) * ratio)
        summary = summary[:char_limit] + "\n[truncated...]"

    return {"role": "system", "content": summary}


class ContextWindowManager:
    def __init__(
        self,
        model_windows: Optional[Dict[str, int]] = None,
        default_window: int = 8192,
        reserve_tokens: int = DEFAULT_RESERVE_TOKENS,
        summarization_threshold: float = 0.85,
    ):
        self._model_windows: Dict[str, int] = {**(model_windows or {})}
        self._default_window: int = default_window
        self._reserve_tokens: int = reserve_tokens
        self._summarization_threshold: float = summarization_threshold

    def get_window(self, model: Optional[str] = None) -> int:
        if model and model in self._model_windows:
            return self._model_windows[model]
        if model:
            if model in MODEL_CONTEXT_WINDOWS:
                return MODEL_CONTEXT_WINDOWS[model]
            for key, window in sorted(MODEL_CONTEXT_WINDOWS.items(), key=lambda x: -len(x[0])):
                if model.lower().startswith(key):
                    return window
            for prefix, window in sorted(MODEL_FAMILY_DEFAULTS.items(), key=lambda x: -len(x[0])):
                if model.lower().startswith(prefix):
                    return window
        return self._default_window

    def set_model_window(self, model: str, window: int) -> None:
        self._model_windows[model] = window

    def manage(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        force_summarize: bool = False,
    ) -> Dict[str, Any]:
        if max_tokens is None:
            max_tokens = self.get_window(model)

        result: Dict[str, Any] = {
            "messages": list(messages),
            "original_count": len(messages),
            "final_count": len(messages),
            "trimmed": 0,
            "summarized": False,
            "summary_message": None,
        }

        token_info = count_messages_tokens(messages, model=model)
        result["total_tokens"] = token_info["total_tokens"]

        if not messages:
            return result

        if force_summarize or should_summarize(messages, max_tokens, self._summarization_threshold):
            sys_msgs = [m for m in messages if m.get("role") == "system"]
            non_sys = messages[len(sys_msgs) :]
            if len(non_sys) > 4:
                keep_recent = non_sys[-4:]
                to_summarize = non_sys[:-4]
                if to_summarize:
                    summary_msg = build_summary_message(to_summarize, model=model)
                    result["messages"] = sys_msgs + [summary_msg] + keep_recent
                    result["summarized"] = True
                    result["summary_message"] = summary_msg
                    result["trimmed"] += len(to_summarize)
                    token_info = count_messages_tokens(result["messages"], model=model)
                    result["total_tokens"] = token_info["total_tokens"]

        trimmed = trim_messages(result["messages"], max_tokens, self._reserve_tokens)
        result["trimmed"] += len(result["messages"]) - len(trimmed)
        result["messages"] = trimmed
        result["final_count"] = len(trimmed)

        if result["final_count"] == 0 and messages:
            result["messages"] = messages[-1:]

        return result
