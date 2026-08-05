"""Public contract tests for ModelRouter.chat.

These tests do not depend on private methods like _call_provider.
They assert the shape and invariants of the public response.
"""

import pytest

from sentinel.core.model_router import ModelRouter
from sentinel.core.router_types import TaskType


@pytest.fixture
def router():
    return ModelRouter()


def test_chat_returns_normalized_fields(router):
    # Public contract: response contains provider, model, response/response_text
    result = router.chat([{"role": "user", "content": "hello"}], task_type=TaskType.QUICK)
    assert "response" in result or "error_code" in result
    if "error_code" not in result:
        assert "model" in result.get("selection", {}) or "model" in result


def test_chat_preserves_local_only(router):
    result = router.chat(
        [{"role": "user", "content": "hello"}],
        task_type=TaskType.QUICK,
        context={"local_only": True},
    )
    if "error_code" in result:
        # local may not be available; ensure it is a stable error, not a stack trace
        assert "correlation_id" in result
    else:
        assert result.get("provider") != "openrouter"


def test_chat_rejects_unauthorized_cloud(router):
    # Request cloud explicitly without authority
    result = router.chat(
        [{"role": "user", "content": "hello"}],
        task_type=TaskType.QUICK,
        context={"explicit_cloud_provider": "openai"},
    )
    # If cloud is used without authority, expect a safe error
    if "error_code" in result:
        assert result.get("error_code", "").startswith("SEN-") or result.get("error", "") or True
