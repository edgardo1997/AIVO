from datetime import timedelta
from pathlib import Path

from sentinel.authorization_manager import (
    AuthorizationManagerControl,
    AuthorizationManagerV2,
)
from sentinel.contracts import (
    ApplicationLaunchTypeV1,
    ApplicationVerificationLevelV1,
    AuthorizationScopeV1,
    LimitedExecutionStatusV1,
    SimulationActionTypeV1,
    ToolCategoryV1,
)
from sentinel.limited_execution_v2 import (
    LimitedExecutionControl,
    LimitedExecutionRequestV1,
    LimitedExecutionV2,
    LimitedOperationV1,
)
from sentinel.operational_telemetry_hub import OperationalTelemetryHub
from sentinel.tool_gateway import (
    PassiveToolGatewayV2,
    ToolGatewayControl,
    ToolParameterValueV1,
    ToolRequestV1,
    canonical_parameters_hash,
)
from test_authorization_manager_v2 import _granted_inputs
from test_versioned_contracts import _descriptor


class FakeBackend:
    def __init__(self, *, fail=False):
        self.calls: list[str] = []
        self.fail = fail

    def system_information(self):
        self.calls.append("system_information")
        if self.fail:
            raise RuntimeError("isolated backend failure")
        return {"system": "Windows", "release": "test", "machine": "x64"}

    def file_metadata(self, path):
        self.calls.append("file_metadata")
        return {"resource_type": "file", "size_bytes": 10, "modified_ns": 1}

    def launch_application(self, descriptor):
        self.calls.append("launch_application")
        return {"application_id": descriptor.application_id, "pid": 42}


def _authorized(tmp_path, operation, *, resource_id=None, application_id=None):
    values, policy, consent, verifier = _granted_inputs(tmp_path / "inputs")
    action = SimulationActionTypeV1(operation.value)
    policy = policy.model_copy(update={"action_type": action})
    consent = consent.model_copy(update={"request_type": action})
    details = {}
    if resource_id is not None:
        details["resource_id"] = resource_id
    if application_id is not None:
        details["application_id"] = application_id
    params_hash = canonical_parameters_hash(details)
    tool_id, category = {
        LimitedOperationV1.SYSTEM_INFORMATION: (
            "sentinel.system.information",
            ToolCategoryV1.SYSTEM_INFORMATION,
        ),
        LimitedOperationV1.FILE_METADATA: (
            "sentinel.file.metadata",
            ToolCategoryV1.FILE_READ,
        ),
        LimitedOperationV1.APPLICATION_LAUNCH: (
            "sentinel.application.launch",
            ToolCategoryV1.APPLICATION_LAUNCH,
        ),
    }[operation]
    scope = (
        AuthorizationScopeV1.USER_APPROVED_ACTION
        if operation is LimitedOperationV1.APPLICATION_LAUNCH
        else AuthorizationScopeV1.READ_ONLY
    )
    auth_hub = OperationalTelemetryHub(
        database_path=tmp_path / "authorization.sqlite3",
        enabled=True,
    )
    manager = AuthorizationManagerV2(
        control=AuthorizationManagerControl(enabled=True),
        verifier=verifier,
        telemetry_hub=auth_hub,
    )
    now = consent.timestamp + timedelta(seconds=1)
    grant = manager.issue_limited_from_consent(
        consent=consent,
        policy=policy,
        evidence=values["evidence"],
        scope=scope,
        params_hash=params_hash,
        plan_id=f"plan:{operation.value.lower()}",
        step_id=f"step:{operation.value.lower()}",
        tool_id=tool_id,
        expires_at=now + timedelta(minutes=3),
        now=now,
    ).grant
    gateway_hub = OperationalTelemetryHub(
        database_path=tmp_path / "gateway.sqlite3",
        enabled=True,
    )
    tool_request = ToolRequestV1(
        request_id=f"gateway:{operation.value.lower()}",
        correlation_id=grant.correlation_id,
        evidence_hash=grant.evidence_hash,
        issuer_id=grant.issuer_id,
        authorization_reference=grant.grant_id,
        plan_id=grant.plan_id,
        step_id=grant.authorized_steps[0].step_id,
        tool_id=tool_id,
        tool_version="1.0.0",
        requested_tool_category=category,
        requested_scope=scope,
        parameters=tuple(ToolParameterValueV1(name=name, value=value) for name, value in details.items()),
        params_hash=params_hash,
        timestamp=now + timedelta(seconds=1),
    )
    gateway = (
        PassiveToolGatewayV2(
            control=ToolGatewayControl(enabled=True),
            verifier=verifier,
            telemetry_hub=gateway_hub,
        )
        .evaluate(
            request=tool_request,
            grant=grant,
            consent=consent,
            evidence=values["evidence"],
            policy=policy,
            now=tool_request.timestamp,
        )
        .decision
    )
    request = LimitedExecutionRequestV1(
        request_id=f"execute:{operation.value.lower()}",
        correlation_id=grant.correlation_id,
        evidence_hash=grant.evidence_hash,
        authorization_id=grant.authorization_id,
        plan_id=grant.plan_id,
        step_id=grant.authorized_steps[0].step_id,
        tool_id=tool_id,
        params_hash=params_hash,
        operation=operation,
        resource_id=resource_id,
        application_id=application_id,
        timestamp=tool_request.timestamp,
    )
    return (
        request,
        grant,
        gateway,
        values["evidence"],
        verifier,
        manager,
        auth_hub,
        gateway_hub,
    )


def _executor(tmp_path, verifier, manager, backend, *, enabled=True):
    hub = OperationalTelemetryHub(
        database_path=tmp_path / "execution.sqlite3",
        enabled=True,
    )
    executor = LimitedExecutionV2(
        control=LimitedExecutionControl(enabled=enabled),
        verifier=verifier,
        consume_grant=manager.consume,
        telemetry_hub=hub,
        backend=backend,
        resource_catalog={"resource.safe": Path("logical-resource")},
    )
    return executor, hub


def test_system_information_executes_only_after_complete_authorization(tmp_path):
    values = _authorized(tmp_path, LimitedOperationV1.SYSTEM_INFORMATION)
    request, grant, gateway, evidence, verifier, manager, auth_hub, gateway_hub = values
    backend = FakeBackend()
    executor, hub = _executor(tmp_path, verifier, manager, backend)
    try:
        receipt = executor.execute(
            request=request,
            grant=grant,
            gateway=gateway,
            evidence=evidence,
            now=request.timestamp,
        )
        assert receipt.status is LimitedExecutionStatusV1.SUCCEEDED
        assert backend.calls == ["system_information"]
        assert receipt.authority is False
        assert hub.timeline.latest()
    finally:
        hub.close()
        auth_hub.close()
        gateway_hub.close()


def test_disabled_and_tampered_requests_never_reach_backend(tmp_path):
    values = _authorized(tmp_path, LimitedOperationV1.SYSTEM_INFORMATION)
    request, grant, gateway, evidence, verifier, manager, auth_hub, gateway_hub = values
    backend = FakeBackend()
    executor, hub = _executor(
        tmp_path,
        verifier,
        manager,
        backend,
        enabled=False,
    )
    try:
        disabled = executor.execute(
            request=request,
            grant=grant,
            gateway=gateway,
            evidence=evidence,
        )
        assert disabled.status is LimitedExecutionStatusV1.BLOCKED
        assert backend.calls == []

        enabled, enabled_hub = _executor(
            tmp_path / "enabled",
            verifier,
            manager,
            backend,
        )
        try:
            changed = request.model_copy(update={"params_hash": "f" * 64})
            blocked = enabled.execute(
                request=changed,
                grant=grant,
                gateway=gateway,
                evidence=evidence,
                now=request.timestamp,
            )
            assert blocked.status is LimitedExecutionStatusV1.BLOCKED
            assert backend.calls == []
        finally:
            enabled_hub.close()
    finally:
        hub.close()
        auth_hub.close()
        gateway_hub.close()


def test_grant_is_single_use_and_replay_is_blocked(tmp_path):
    values = _authorized(tmp_path, LimitedOperationV1.SYSTEM_INFORMATION)
    request, grant, gateway, evidence, verifier, manager, auth_hub, gateway_hub = values
    backend = FakeBackend()
    executor, hub = _executor(tmp_path, verifier, manager, backend)
    try:
        first = executor.execute(
            request=request,
            grant=grant,
            gateway=gateway,
            evidence=evidence,
            now=request.timestamp,
        )
        second = executor.execute(
            request=request,
            grant=grant,
            gateway=gateway,
            evidence=evidence,
            now=request.timestamp,
        )
        assert first.status is LimitedExecutionStatusV1.SUCCEEDED
        assert second.status is LimitedExecutionStatusV1.BLOCKED
        assert second.result_code == "AUTHORIZATION_REPLAYED"
        assert backend.calls == ["system_information"]
    finally:
        hub.close()
        auth_hub.close()
        gateway_hub.close()


def test_metadata_uses_trusted_resource_id_not_user_path(tmp_path):
    values = _authorized(
        tmp_path,
        LimitedOperationV1.FILE_METADATA,
        resource_id="resource.safe",
    )
    request, grant, gateway, evidence, verifier, manager, auth_hub, gateway_hub = values
    backend = FakeBackend()
    executor, hub = _executor(tmp_path, verifier, manager, backend)
    try:
        receipt = executor.execute(
            request=request,
            grant=grant,
            gateway=gateway,
            evidence=evidence,
            now=request.timestamp,
        )
        assert receipt.status is LimitedExecutionStatusV1.SUCCEEDED
        assert "path" not in receipt.sanitized_result
        assert backend.calls == ["file_metadata"]
    finally:
        hub.close()
        auth_hub.close()
        gateway_hub.close()


def test_backend_failure_returns_receipt_and_logical_fallback(tmp_path):
    values = _authorized(tmp_path, LimitedOperationV1.SYSTEM_INFORMATION)
    request, grant, gateway, evidence, verifier, manager, auth_hub, gateway_hub = values
    executor, hub = _executor(tmp_path, verifier, manager, FakeBackend(fail=True))
    try:
        receipt = executor.execute(
            request=request,
            grant=grant,
            gateway=gateway,
            evidence=evidence,
            now=request.timestamp,
        )
        assert receipt.status is LimitedExecutionStatusV1.FALLBACK_REQUIRED
        assert receipt.fallback_available is True
        assert receipt.rollback_state == "FALLBACK_AVAILABLE"
    finally:
        hub.close()
        auth_hub.close()
        gateway_hub.close()


def test_only_verified_application_descriptor_can_launch(tmp_path):
    values = _authorized(
        tmp_path,
        LimitedOperationV1.APPLICATION_LAUNCH,
        application_id="app_executable",
    )
    request, grant, gateway, evidence, verifier, manager, auth_hub, gateway_hub = values
    descriptor = _descriptor(
        ApplicationLaunchTypeV1.EXECUTABLE,
        "C:\\Windows\\System32\\notepad.exe",
        "C:\\Windows\\System32\\notepad.exe",
    )
    backend = FakeBackend()
    executor, hub = _executor(tmp_path, verifier, manager, backend)
    try:
        receipt = executor.execute(
            request=request,
            grant=grant,
            gateway=gateway,
            evidence=evidence,
            descriptor=descriptor,
            now=request.timestamp,
        )
        assert receipt.status is LimitedExecutionStatusV1.SUCCEEDED
        assert receipt.application_receipt is not None
        assert receipt.application_receipt.state.value == "launch_requested"
        assert backend.calls == ["launch_application"]
    finally:
        hub.close()
        auth_hub.close()
        gateway_hub.close()

    other = _authorized(
        tmp_path / "unverified",
        LimitedOperationV1.APPLICATION_LAUNCH,
        application_id="app_executable",
    )
    (
        request,
        grant,
        gateway,
        evidence,
        verifier,
        manager,
        auth_hub,
        gateway_hub,
    ) = other
    unverified = descriptor.model_copy(update={"verification_level": ApplicationVerificationLevelV1.DISCOVERED})
    executor, hub = _executor(
        tmp_path / "unverified",
        verifier,
        manager,
        backend,
    )
    try:
        blocked = executor.execute(
            request=request,
            grant=grant,
            gateway=gateway,
            evidence=evidence,
            descriptor=unverified,
            now=request.timestamp,
        )
        assert blocked.status is LimitedExecutionStatusV1.BLOCKED
        assert backend.calls == ["launch_application"]
    finally:
        hub.close()
        auth_hub.close()
        gateway_hub.close()


def test_timeout_produces_receipt_without_automatic_legacy_execution(
    tmp_path,
    monkeypatch,
):
    values = _authorized(tmp_path, LimitedOperationV1.SYSTEM_INFORMATION)
    request, grant, gateway, evidence, verifier, manager, auth_hub, gateway_hub = values
    executor, hub = _executor(tmp_path, verifier, manager, FakeBackend())
    observed = iter((0.0, 10.0))
    monkeypatch.setattr(
        "sentinel.limited_execution_v2.executor.monotonic",
        lambda: next(observed),
    )
    try:
        receipt = executor.execute(
            request=request,
            grant=grant,
            gateway=gateway,
            evidence=evidence,
            now=request.timestamp,
        )
        assert receipt.status is LimitedExecutionStatusV1.TIMED_OUT
        assert receipt.rollback_state == "LOGICAL_ONLY"
        assert receipt.fallback_available is True
    finally:
        hub.close()
        auth_hub.close()
        gateway_hub.close()
