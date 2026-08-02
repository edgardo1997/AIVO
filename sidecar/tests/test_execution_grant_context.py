import pytest

from sentinel.security.models import ExecutionGrantContext
from sentinel.core.confirmation import ConfirmationBroker


def _context(**changes):
    data = dict(grant_id="g", plan_grant_id="p", step_grant_id="s", user_id="u", session_id="session", identity_hash="ih", plan_id="plan", plan_hash="ph", step_id="step", step_index=0, tool_id="tool", params_hash="args", approved_at="2026-01-01T00:00:00Z", expires_at="2026-01-01T00:10:00Z")
    data.update(changes)
    return ExecutionGrantContext(**data)


def test_grant_context_is_immutable_and_canonical():
    context = _context()
    assert context.canonical_json() == _context().canonical_json()
    with pytest.raises(Exception):
        context.user_id = "other"


@pytest.mark.parametrize("changes", [{"user_id": ""}, {"step_index": -1}, {"params_hash": ""}])
def test_grant_context_rejects_incomplete_bindings(changes):
    with pytest.raises(ValueError):
        _context(**changes)


def test_canonical_plan_is_order_independent():
    first = {"steps": [{"tool_id": "tool", "params": {"b": 2, "a": 1}}], "plan_id": "p"}
    second = {"plan_id": "p", "steps": [{"params": {"a": 1, "b": 2}, "tool_id": "tool"}]}
    assert ConfirmationBroker.canonical_plan(first) == ConfirmationBroker.canonical_plan(second)
