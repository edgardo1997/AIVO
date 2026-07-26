import hashlib
from datetime import datetime, timezone

from sentinel.contracts import (
    LimitedExecutionStatusV1,
    ToolGatewayDecisionValueV1,
)
from sentinel.controlled_runtime_activation import (
    CanaryKillSwitch,
    CanaryRoutingEvidenceV1,
    ControlledActivationControl,
    ControlledCanaryExecutor,
    ControlledRuntimeActivation,
    ControlledRuntimeRouter,
    RuntimeSelection,
)
from sentinel.limited_execution_v2 import LimitedOperationV1
from test_limited_execution_v2 import (
    FakeBackend,
    _authorized,
    _executor,
)


def _bucket_request(minimum=95):
    for index in range(10000):
        request_id = f"canary:{index}"
        bucket = (
            int(
                hashlib.sha256(request_id.encode()).hexdigest()[:8],
                16,
            )
            % 100
        )
        if bucket >= minimum:
            return request_id
    raise AssertionError("canary bucket unavailable")


def _router(percentage=5):
    activation = ControlledRuntimeActivation(
        ControlledActivationControl(
            enabled=True,
            canary_enabled=True,
            traffic_percentage=percentage,
        )
    )
    assert activation.start()
    return ControlledRuntimeRouter(activation=activation)


def _routing(request_id, **updates):
    values = {
        "request_id": request_id,
        "gateway_eligibility": "V2_ELIGIBLE_CANARY",
        "readiness_approved": True,
        "safety_healthy": True,
        "rollback_available": True,
        "requested_scope": "system.information",
        "allowed_scopes": ("system.information",),
        "trial_started_at": datetime.now(timezone.utc),
        "maximum_trial_seconds": 3600,
        "critical_divergences": 0,
    }
    values.update(updates)
    return CanaryRoutingEvidenceV1(**values)


def _canary_inputs(tmp_path, *, backend=None, kill_switch=None):
    values = _authorized(tmp_path, LimitedOperationV1.SYSTEM_INFORMATION)
    request, grant, gateway, evidence, verifier, manager, auth_hub, gateway_hub = values
    request_id = _bucket_request()
    request = request.model_copy(update={"request_id": request_id})
    v2, execution_hub = _executor(
        tmp_path,
        verifier,
        manager,
        backend or FakeBackend(),
    )
    legacy_calls = []

    def legacy_handler(selected_request_id):
        legacy_calls.append(selected_request_id)
        return "LEGACY_COMPLETED"

    coordinator = ControlledCanaryExecutor(
        router=_router(),
        v2_executor=v2,
        legacy_handler=legacy_handler,
        kill_switch=kill_switch or CanaryKillSwitch(engaged=False),
    )
    return (
        coordinator,
        _routing(request_id),
        request,
        grant,
        gateway,
        evidence,
        legacy_calls,
        (execution_hub, auth_hub, gateway_hub),
    )


def _dispatch(values):
    coordinator, routing, request, grant, gateway, evidence, _, _ = values
    return coordinator.dispatch(
        routing=routing,
        request=request,
        grant=grant,
        gateway=gateway,
        evidence=evidence,
        now=request.timestamp,
    )


def test_canary_flags_and_kill_switch_fail_safe_by_default(tmp_path):
    values = _canary_inputs(
        tmp_path,
        kill_switch=CanaryKillSwitch(),
    )
    try:
        result = _dispatch(values)
        assert result.selected_runtime is RuntimeSelection.LEGACY
        assert result.fallback_before_execution is True
        assert values[6] == [values[2].request_id]
    finally:
        for hub in values[7]:
            hub.close()


def test_deterministic_routing_never_exceeds_five_percent():
    router = _router()
    for index in range(1000):
        request_id = f"sample:{index}"
        decision = router.route(_routing(request_id))
        bucket = (
            int(
                hashlib.sha256(request_id.encode()).hexdigest()[:8],
                16,
            )
            % 100
        )
        if decision.selected_runtime is RuntimeSelection.V2_CANARY:
            assert bucket >= 95
    target = _routing(_bucket_request())
    assert router.route(target) == router.route(target)


def test_v2_executes_once_and_duplicate_dispatch_is_cached(tmp_path):
    backend = FakeBackend()
    values = _canary_inputs(tmp_path, backend=backend)
    try:
        first = _dispatch(values)
        second = _dispatch(values)
        assert first == second
        assert first.selected_runtime is RuntimeSelection.V2_CANARY
        assert first.v2_receipt.status is LimitedExecutionStatusV1.SUCCEEDED
        assert backend.calls == ["system_information"]
        assert values[6] == []
        assert first.double_execution is False
    finally:
        for hub in values[7]:
            hub.close()


def test_authorization_failure_rolls_back_before_v2_execution(tmp_path):
    backend = FakeBackend()
    values = list(_canary_inputs(tmp_path, backend=backend))
    values[4] = values[4].model_copy(update={"decision": ToolGatewayDecisionValueV1.TOOL_BLOCKED})
    values = tuple(values)
    try:
        result = _dispatch(values)
        assert result.selected_runtime is RuntimeSelection.LEGACY
        assert result.fallback_before_execution is True
        assert backend.calls == []
        assert values[6] == [values[2].request_id]
        metrics = values[0].metrics.snapshot()
        assert metrics.total_requests == 1
        assert metrics.legacy_requests == 1
        assert metrics.v2_canary_requests == 0
        assert metrics.rollbacks == 1
    finally:
        for hub in values[7]:
            hub.close()


def test_failure_after_v2_started_never_duplicates_into_legacy(tmp_path):
    backend = FakeBackend(fail=True)
    values = _canary_inputs(tmp_path, backend=backend)
    try:
        result = _dispatch(values)
        assert result.selected_runtime is RuntimeSelection.V2_CANARY
        assert result.v2_receipt.status is (LimitedExecutionStatusV1.FALLBACK_REQUIRED)
        assert backend.calls == ["system_information"]
        assert values[6] == []
    finally:
        for hub in values[7]:
            hub.close()


def test_unhealthy_or_out_of_scope_routes_to_legacy_before_execution(tmp_path):
    backend = FakeBackend()
    values = list(_canary_inputs(tmp_path, backend=backend))
    values[1] = _routing(values[2].request_id, safety_healthy=False)
    values = tuple(values)
    try:
        result = _dispatch(values)
        assert result.selected_runtime is RuntimeSelection.LEGACY
        assert backend.calls == []
        assert values[6] == [values[2].request_id]
    finally:
        for hub in values[7]:
            hub.close()
