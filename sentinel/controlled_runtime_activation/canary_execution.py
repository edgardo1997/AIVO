"""Exactly-once coordinator for limited V2 canary operations."""

from __future__ import annotations

from datetime import datetime
from typing import Callable

from pydantic import BaseModel, ConfigDict

from sentinel.contracts import (
    ApplicationDescriptorV1,
    AuthorizationGrantV1,
    AuthorizationStatusV1,
    EvidenceSignalV1,
    LimitedExecutionReceiptV1,
    LimitedExecutionStatusV1,
    ToolGatewayDecisionResultV1,
    ToolGatewayDecisionValueV1,
)
from sentinel.limited_execution_v2 import (
    LimitedExecutionRequestV1,
    LimitedExecutionV2,
)

from .canary_policy import CanaryRoutingEvidenceV1
from .kill_switch import CanaryKillSwitch
from .metrics import ActivationMetrics
from .router import ControlledRuntimeRouter, RuntimeSelection


class CanaryExecutionResultV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    request_id: str
    selected_runtime: RuntimeSelection
    result_code: str
    v2_receipt: LimitedExecutionReceiptV1 | None = None
    fallback_before_execution: bool = False
    double_execution: bool = False


class ControlledCanaryExecutor:
    """Routes once; fallback is allowed only before V2 backend invocation."""

    def __init__(
        self,
        *,
        router: ControlledRuntimeRouter,
        v2_executor: LimitedExecutionV2,
        legacy_handler: Callable[[str], str],
        kill_switch: CanaryKillSwitch,
        metrics: ActivationMetrics | None = None,
    ) -> None:
        self.router = router
        self.v2_executor = v2_executor
        self.legacy_handler = legacy_handler
        self.kill_switch = kill_switch
        self.metrics = metrics or router.metrics
        self._results: dict[str, CanaryExecutionResultV1] = {}

    def dispatch(
        self,
        *,
        routing: CanaryRoutingEvidenceV1,
        request: LimitedExecutionRequestV1,
        grant: AuthorizationGrantV1,
        gateway: ToolGatewayDecisionResultV1,
        evidence: EvidenceSignalV1,
        descriptor: ApplicationDescriptorV1 | None = None,
        now: datetime | None = None,
    ) -> CanaryExecutionResultV1:
        existing = self._results.get(routing.request_id)
        if existing is not None:
            return existing
        if routing.request_id != request.request_id:
            return self._legacy(
                routing.request_id,
                "REQUEST_ID_MISMATCH",
                fallback=True,
                route_was_counted=False,
            )
        if self.kill_switch.engaged:
            return self._legacy(
                routing.request_id,
                f"KILL_SWITCH:{self.kill_switch.reason}",
                fallback=True,
                route_was_counted=False,
            )
        route = self.router.route(routing)
        if route.selected_runtime is RuntimeSelection.LEGACY:
            return self._legacy(
                routing.request_id,
                route.reason_codes[0],
                fallback=False,
                route_was_counted=True,
            )
        if self.kill_switch.engaged:
            return self._legacy(
                routing.request_id,
                f"KILL_SWITCH:{self.kill_switch.reason}",
                fallback=True,
                route_was_counted=True,
                route_was_v2=True,
            )
        preflight_error = _authorization_precheck(request, grant, gateway)
        if preflight_error is not None:
            return self._legacy(
                routing.request_id,
                f"AUTHORIZATION_PREFLIGHT:{preflight_error}",
                fallback=True,
                route_was_counted=True,
                route_was_v2=True,
            )
        receipt = self.v2_executor.execute(
            request=request,
            grant=grant,
            gateway=gateway,
            evidence=evidence,
            descriptor=descriptor,
            now=now,
        )
        if receipt.status is LimitedExecutionStatusV1.BLOCKED:
            return self._legacy(
                routing.request_id,
                f"V2_PREFLIGHT_BLOCKED:{receipt.result_code}",
                fallback=True,
                receipt=receipt,
                route_was_counted=True,
                route_was_v2=True,
            )
        result = CanaryExecutionResultV1(
            request_id=routing.request_id,
            selected_runtime=RuntimeSelection.V2_CANARY,
            result_code=receipt.result_code,
            v2_receipt=receipt,
        )
        self._results[routing.request_id] = result
        return result

    def _legacy(
        self,
        request_id: str,
        reason: str,
        *,
        fallback: bool,
        route_was_counted: bool,
        route_was_v2: bool = False,
        receipt: LimitedExecutionReceiptV1 | None = None,
    ) -> CanaryExecutionResultV1:
        if fallback:
            self.metrics.record_pre_execution_fallback(
                route_was_v2=route_was_v2,
                route_was_counted=route_was_counted,
            )
        result_code = self.legacy_handler(request_id)
        result = CanaryExecutionResultV1(
            request_id=request_id,
            selected_runtime=RuntimeSelection.LEGACY,
            result_code=f"{reason}:{result_code}",
            v2_receipt=receipt,
            fallback_before_execution=fallback,
        )
        self._results[request_id] = result
        return result


def _authorization_precheck(
    request: LimitedExecutionRequestV1,
    grant: AuthorizationGrantV1,
    gateway: ToolGatewayDecisionResultV1,
) -> str | None:
    if grant.status is not AuthorizationStatusV1.AUTHORIZED_LIMITED:
        return "GRANT_NOT_LIMITED"
    if grant.revoked or grant.consumed_at is not None:
        return "GRANT_UNUSABLE"
    if gateway.decision is not ToolGatewayDecisionValueV1.TOOL_ALLOWED:
        return "GATEWAY_NOT_ALLOWED"
    if request.authorization_id != grant.authorization_id or gateway.authorization_reference != grant.grant_id:
        return "AUTHORIZATION_MISMATCH"
    if (
        request.correlation_id != grant.correlation_id
        or request.correlation_id != gateway.correlation_id
        or request.plan_id != grant.plan_id
        or request.plan_id != gateway.plan_id
        or request.step_id != gateway.step_id
        or request.tool_id != gateway.tool_id
        or request.params_hash != gateway.params_hash
    ):
        return "BINDING_MISMATCH"
    return None
