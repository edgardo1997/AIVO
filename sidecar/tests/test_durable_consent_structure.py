"""P0-1 structural regression tests.

These fail if a legacy approval path is restored as authority, if a raw
PendingActionRecord is ever treated as an execution grant, or if the durable
plan-grant factory leaks outside ConfirmationBroker.
"""
import ast
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[2]

PRODUCTION_DIRS = (
    ROOT / "sentinel" / "core",
    ROOT / "sentinel" / "security",
    ROOT / "sentinel" / "tools",
    ROOT / "sentinel" / "routing",
    ROOT / "sentinel" / "execution",
    ROOT / "sidecar" / "modules",
    ROOT / "sidecar" / "routers",
    ROOT / "sidecar" / "services",
    ROOT / "sidecar" / "repositories",
)

# Files that may legitimately reference the durable factory primitives.
DEFINITION_FILES = frozenset({
    "sentinel/core/confirmation.py",
    "sentinel/core/orchestrator.py",
    "sidecar/repositories/execution_grant_repository.py",
})

# The v1 plans router is the single production seam that consumes the durable
# plan factory (request/approve/resume) on behalf of authenticated callers.  No
# other production module may reach the durable authority primitives directly.
PRODUCTION_WIRE_FILES = frozenset({
    "sidecar/routers/v1/plans.py",
})

ALLOWED_FILES = DEFINITION_FILES | PRODUCTION_WIRE_FILES

FACTORY_TOKENS = ("request_plan_grant", "approve_plan_grant", "resume_approved_plan", "create_plan(")


@pytest.mark.unit
def test_durable_plan_grant_factory_wired_only_through_broker_and_v1_router():
    """The durable authority primitives are reachable only via ConfirmationBroker
    and the single v1 plans production seam.

    ConfirmationBroker owns the authority.  The only non-library consumer is the
    v1 plans router (approve/resume).  Any other module referencing the factory
    would be a leak of authority outside the controlled consent flow.
    """
    violations = []
    for directory in PRODUCTION_DIRS:
        if not directory.exists():
            continue
        for pyfile in directory.rglob("*.py"):
            rel = str(pyfile.relative_to(ROOT)).replace("\\", "/")
            if rel in ALLOWED_FILES:
                continue
            content = pyfile.read_text(encoding="utf-8")
            for token in FACTORY_TOKENS:
                if token in content:
                    violations.append(f"{rel}: references {token}")
    assert not violations, "Durable grant factory referenced outside ConfirmationBroker / v1-plans:\n" + "\n".join(violations)


@pytest.mark.unit
def test_legacy_approval_apis_never_call_execution_pipeline_or_process():
    """approve_execution/approve_with_modifications must return authority-free results."""
    import inspect

    from sentinel.core.orchestrator import Orchestrator

    for method in ("approve_execution", "approve_with_modifications"):
        source = inspect.getsource(getattr(Orchestrator, method))
        for forbidden in ("self.process(", "self._execution_pipeline.execute", "self._tool_gateway.execute", "gateway.execute"):
            assert forbidden not in source, f"{method} still reaches {forbidden}"


@pytest.mark.asyncio
async def test_approve_execution_and_modifications_never_execute():
    """Runtime proof: deprecated approvals return an error and never reach the pipeline."""
    from sentinel.core.orchestrator import Orchestrator
    from sentinel.core.execution_pipeline import ExecutionPipeline

    class _ExplodingPipeline(ExecutionPipeline):
        async def execute(self, *args, **kwargs):  # pragma: no cover
            raise AssertionError("legacy approval must never reach the pipeline")

    orch = Orchestrator(
        intent_engine=MagicMock(),
        tool_gateway=MagicMock(),
        execution_pipeline=_ExplodingPipeline(),
        audit_service=MagicMock(),
    )
    approved = await orch.approve_execution("action-1", True, {"user_id": "u"})
    assert approved.error and "deprecated" in approved.error
    modified = await orch.approve_with_modifications("action-1", [{"tool_id": "t", "params": {}}], {"user_id": "u"})
    assert modified.error and "deprecated" in modified.error


@pytest.mark.unit
def test_raw_pending_action_never_yields_typed_grant():
    """A PendingActionRecord consumed directly is not an ExecutionGrantContext."""
    from sentinel.core.operational_memory import InMemoryBackend, OperationalMemoryConfig, PendingActionRecord
    from sentinel.security.models import ExecutionGrantContext
    from datetime import datetime, timezone

    mem = InMemoryBackend(config=OperationalMemoryConfig(max_pending_actions=100))
    mem._stop_eviction.set()
    mem.store_pending_action(PendingActionRecord(
        action_id="raw-1", tool_id="executor.command", params={"user_id": "u", "kind": "tool_confirmation"},
        reason="r", created_at=datetime.now(timezone.utc).isoformat(), ttl_seconds=600,
    ))
    record = mem.consume_pending_action("raw-1", expected_user_id="u")
    assert record is not None
    assert not isinstance(record, ExecutionGrantContext)


@pytest.mark.asyncio
async def test_untyped_execution_grant_is_rejected_by_guard():
    """A dict masquerading as a step grant is denied before any execution."""
    from sentinel.core.policy import PolicyEffect
    from sentinel.core.policy_engine import PolicyEngine
    from sentinel.core.tool import Tool, ToolResult, ToolSpec
    from sentinel.core.tool_gateway import ToolGateway
    from sentinel.security.tool_guard import ToolExecutionGuard
    from sentinel.security.models import ToolRequest

    class _ProbeTool(Tool):
        def spec(self):
            return ToolSpec("probe.tool", "probe", "p", "1", {}, ["probe.execute"])

        async def execute(self, params, context):
            raise AssertionError("probe tool must not execute")

    gateway = ToolGateway(policy_engine=PolicyEngine(default_effect=PolicyEffect.ALLOW))
    gateway.register(_ProbeTool())
    guard = ToolExecutionGuard(tool_gateway=gateway, policy_engine=gateway._policy_engine, audit_service=MagicMock())
    request = ToolRequest(
        tool_name="probe.tool",
        arguments={},
        source="approved_plan",
        user_context={"execution_grant": {"step_grant_id": "forged"}},
        user_id="u",
        session_id="s",
    )
    result = await guard.execute(request)
    assert not result.success
    assert "ExecutionGrantContext" in (result.error or "")
