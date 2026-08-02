"""Event emission tests for AutomationEngine and AIWorkflows (FASE 11 fix).

Verifies that the engines await EventBus.emit correctly (no unawaited
coroutines), that emitted events carry the right payload, and that
subscribers actually receive them. The fix follows the established
``trigger.py`` pattern: run the emit synchronously when no loop is running,
otherwise schedule it as a task.
"""

import asyncio
import gc
import os
import sys
import time
import warnings

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

from sentinel.core.event_bus import EventBus
from sentinel.core import event_types
from sentinel.core.automation_engine import AutomationEngine
from sentinel.core.ai_workflows import AIWorkflows


def _automation_engine(bus):
    return AutomationEngine(event_bus=bus)


def _workflows(bus):
    return AIWorkflows(event_bus=bus)


# ── Event content (evento emitido correctamente) ────────────────────────
def test_automation_rule_added_event_content():
    received = []

    async def handler(event):
        received.append(event)

    bus = EventBus()
    bus.subscribe(event_types.AUTOMATION_RULE_ADDED, handler)
    engine = _automation_engine(bus)
    result = engine.add_rule("r1", "cpu>80", "notify", session_id="sess-1", request_id="req-1")
    assert result["added"] is True
    assert len(received) == 1
    event = received[0]
    assert event.event_type == event_types.AUTOMATION_RULE_ADDED
    assert event.component == "automation_engine"
    assert event.session_id == "sess-1"
    assert event.request_id == "req-1"
    assert event.details == {"rule_id": "r1", "condition": "cpu>80", "action": "notify"}


def test_automation_rule_removed_event_content():
    received = []

    async def handler(event):
        received.append(event)

    bus = EventBus()
    bus.subscribe(event_types.AUTOMATION_RULE_REMOVED, handler)
    engine = _automation_engine(bus)
    engine.add_rule("r1", "cpu>80", "notify")
    engine.remove_rule("r1")
    assert len(received) == 1
    assert received[0].event_type == event_types.AUTOMATION_RULE_REMOVED
    assert received[0].details == {"rule_id": "r1"}


def test_automation_rule_triggered_event_content():
    received = []

    async def handler(event):
        received.append(event)

    bus = EventBus()
    bus.subscribe(event_types.AUTOMATION_RULE_TRIGGERED, handler)
    engine = _automation_engine(bus)
    engine.add_rule("r1", "cpu>80", "notify")
    engine.trigger_rule("r1")
    assert len(received) == 1
    assert received[0].event_type == event_types.AUTOMATION_RULE_TRIGGERED
    assert received[0].details == {"rule_id": "r1", "count": 1}


def test_automation_action_executed_event_content():
    received = []

    async def handler(event):
        received.append(event)

    bus = EventBus()
    bus.subscribe(event_types.AUTOMATION_ACTION_EXECUTED, handler)
    engine = _automation_engine(bus)
    engine.execute_action("shutdown")
    assert len(received) == 1
    assert received[0].event_type == event_types.AUTOMATION_ACTION_EXECUTED
    assert received[0].details == {"action": "shutdown"}


def test_workflow_created_event_content():
    received = []

    async def handler(event):
        received.append(event)

    bus = EventBus()
    bus.subscribe(event_types.WORKFLOW_CREATED, handler)
    workflows = _workflows(bus)
    result = workflows.create("deploy", ["build", "test"], session_id="sess-2")
    assert result["created"] is True
    assert len(received) == 1
    event = received[0]
    assert event.event_type == event_types.WORKFLOW_CREATED
    assert event.component == "ai_workflows"
    assert event.session_id == "sess-2"
    assert event.details["workflow_id"] == result["workflow_id"]
    assert event.details["name"] == "deploy"
    assert event.details["steps"] == 2


def test_workflow_lifecycle_events_content():
    received = []

    async def handler(event):
        received.append(event)

    bus = EventBus()
    for event_type in (
        event_types.WORKFLOW_CREATED,
        event_types.WORKFLOW_STARTED,
        event_types.WORKFLOW_STEP_EXECUTED,
        event_types.WORKFLOW_COMPLETED,
        event_types.WORKFLOW_FAILED,
        event_types.WORKFLOW_CANCELLED,
    ):
        bus.subscribe(event_type, handler)

    workflows = _workflows(bus)
    wf = workflows.create("cycle", ["a", "b"])
    wid = wf["workflow_id"]
    workflows.start(wid)
    workflows.execute_step(wid, step_result="ok")
    workflows.complete(wid)
    broken = workflows.create("broken", ["x"])
    workflows.fail(broken["workflow_id"], error="boom")
    cancelled = workflows.create("cancelled", ["y"])
    workflows.cancel(cancelled["workflow_id"])

    types = [e.event_type for e in received]
    assert types == [
        event_types.WORKFLOW_CREATED,
        event_types.WORKFLOW_STARTED,
        event_types.WORKFLOW_STEP_EXECUTED,
        event_types.WORKFLOW_COMPLETED,
        event_types.WORKFLOW_CREATED,
        event_types.WORKFLOW_FAILED,
        event_types.WORKFLOW_CREATED,
        event_types.WORKFLOW_CANCELLED,
    ]
    assert all(e.component == "ai_workflows" for e in received)


# ── Subscriber delivery (subscriber recibe evento) ──────────────────────


def test_subscriber_receives_automation_event_wildcard():
    received = []

    async def handler(event):
        received.append(event)

    bus = EventBus()
    bus.subscribe("*", handler)
    engine = _automation_engine(bus)
    engine.add_rule("r9", "mem>90", "alert")
    assert len(received) == 1
    assert received[0].event_type == event_types.AUTOMATION_RULE_ADDED


def test_multiple_subscribers_receive_event():
    received_a = []
    received_b = []

    async def handler_a(event):
        received_a.append(event)

    async def handler_b(event):
        received_b.append(event)

    bus = EventBus()
    bus.subscribe(event_types.AUTOMATION_RULE_ADDED, handler_a)
    bus.subscribe(event_types.AUTOMATION_RULE_ADDED, handler_b)
    engine = _automation_engine(bus)
    engine.add_rule("r10", "cpu>95", "alert")
    assert len(received_a) == 1
    assert len(received_b) == 1


# ── No unawaited-coroutine RuntimeWarning ───────────────────────────────


def _assert_no_unawaited_coroutine_warning(fn):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        fn()
        gc.collect()
    unawaited = [
        w
        for w in caught
        if issubclass(w.category, RuntimeWarning) and "never awaited" in str(w.message)
    ]
    assert unawaited == [], f"unawaited coroutine warnings: {[str(w.message) for w in unawaited]}"


def test_no_unawaited_coroutine_warning_automation_engine():
    def run():
        engine = _automation_engine(EventBus())
        engine.add_rule("w1", "cpu>80", "notify")
        engine.trigger_rule("w1")
        engine.execute_action("notify")
        engine.remove_rule("w1")

    _assert_no_unawaited_coroutine_warning(run)


def test_no_unawaited_coroutine_warning_ai_workflows():
    def run():
        workflows = _workflows(EventBus())
        wf = workflows.create("wf", ["a"])
        wid = wf["workflow_id"]
        workflows.start(wid)
        workflows.execute_step(wid, step_result="ok")
        workflows.complete(wid)
        workflows.fail("gone", error="x")

    _assert_no_unawaited_coroutine_warning(run)


def test_no_unawaited_coroutine_warning_with_active_subscriber():
    async def handler(event):
        return None

    bus = EventBus()
    bus.subscribe(event_types.AUTOMATION_RULE_ADDED, handler)
    engine = _automation_engine(bus)
    _assert_no_unawaited_coroutine_warning(lambda: engine.add_rule("w2", "a", "b"))


# ── Async context (task scheduling inside a running loop) ───────────────


async def _wait_for(cond, timeout=1.0):
    deadline = time.monotonic() + timeout
    while not cond():
        if time.monotonic() > deadline:
            raise TimeoutError("event not delivered within timeout")
        await asyncio.sleep(0.01)


@pytest.mark.asyncio
async def test_async_context_dispatches_event():
    received = []

    async def handler(event):
        received.append(event)

    bus = EventBus()
    bus.subscribe(event_types.AUTOMATION_RULE_ADDED, handler)
    engine = _automation_engine(bus)
    engine.add_rule("a1", "cpu>80", "notify")
    await _wait_for(lambda: len(received) == 1)
    assert len(received) == 1
    assert received[0].details["rule_id"] == "a1"


@pytest.mark.asyncio
async def test_async_context_workflow_dispatches_event():
    received = []

    async def handler(event):
        received.append(event)

    bus = EventBus()
    bus.subscribe(event_types.WORKFLOW_CREATED, handler)
    workflows = _workflows(bus)
    workflows.create("aflow", ["x"])
    await _wait_for(lambda: len(received) == 1)
    assert len(received) == 1
    assert received[0].details["name"] == "aflow"
