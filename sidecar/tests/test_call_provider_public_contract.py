"""Public contract for ProviderManager.call_provider (legacy wrapper)."""

import pytest
from unittest.mock import MagicMock

from sentinel.core.router_types import ProviderSpec, RouterDecision, TaskType
from sentinel.providers.provider_manager import ProviderManager


def _local_provider():
    return ProviderSpec(id="sentinel_local", name="sentinel_local", task_types=[TaskType.QUICK], is_local=True)


def _decision():
    return RouterDecision(provider_id="sentinel_local", model="Qwen3-1.7B-Q8_0.gguf", task_type=TaskType.QUICK, strategy="priority", reason="local")


def test_call_provider_logs_legacy_warning_and_returns_result():
    pm = ProviderManager()
    result = pm.call_provider(_decision(), _local_provider(), [{"role": "user", "content": "hi"}])
    # Public contract: must contain response and selection-relevant fields
    assert "response" in result
    assert "usage" in result
    assert "tool_calls" in result
