"""Controlled coordination of an injected shadow pipeline."""

import time
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from .comparison import compare_runtime
from .control import RuntimeV2ActivationState, RuntimeV2Control
from .diagnostics import (
    ControlledRuntimeDiagnostics,
    RuntimeShadowResultV1,
)


class ControlledRuntimePipeline:
    """Return diagnostics only; injected shadow output is never exposed."""

    def __init__(
        self,
        *,
        control: RuntimeV2Control,
        shadow_pipeline: Any | None = None,
        diagnostics: ControlledRuntimeDiagnostics | None = None,
    ) -> None:
        self.control = control
        self._shadow_pipeline = shadow_pipeline
        self.diagnostics = diagnostics or ControlledRuntimeDiagnostics()

    def observe(
        self,
        legacy_snapshot: Any,
        *,
        legacy_status: str,
        legacy_comparison: dict | None = None,
    ) -> RuntimeShadowResultV1:
        timestamp = datetime.now(timezone.utc)
        correlation_id = f"v2_shadow_{uuid.uuid4().hex}"
        if self.control.state is RuntimeV2ActivationState.DISABLED:
            return RuntimeShadowResultV1(
                schema_version="1.0",
                correlation_id=correlation_id,
                timestamp=timestamp,
                legacy_status=_safe_status(legacy_status),
                shadow_status="DISABLED",
                warnings=("v2_routing_disabled",),
                authority=False,
            )
        started = time.perf_counter()
        errors: list[str] = []
        warnings: list[str] = []
        shadow_output = None
        if self._shadow_pipeline is None:
            errors.append("shadow_pipeline_unavailable")
        else:
            try:
                shadow_output = self._shadow_pipeline.observe(deepcopy(legacy_snapshot))
            except Exception:
                errors.append("shadow_pipeline_failure")
        shadow_summary = _shadow_summary(shadow_output)
        if self.control.state is RuntimeV2ActivationState.COMPARISON_ENABLED:
            comparison = compare_runtime(
                legacy_comparison,
                shadow_summary,
                shadow_errors=tuple(errors),
            )
            differences = (
                (comparison.status.value,) if comparison.status.value != "MATCH" else ()
            ) + comparison.differences
        else:
            differences = ()
            if self.control.diagnostic_mode and shadow_output is None:
                warnings.append("shadow_result_unavailable")
        result = RuntimeShadowResultV1(
            schema_version="1.0",
            correlation_id=correlation_id,
            timestamp=timestamp,
            legacy_status=_safe_status(legacy_status),
            shadow_status=("ERROR" if errors else "OBSERVED"),
            differences=tuple(differences),
            warnings=tuple(warnings),
            errors=tuple(errors),
            authority=False,
        )
        self.diagnostics.record(
            result,
            latency_ms=(time.perf_counter() - started) * 1000,
        )
        return result


def _shadow_summary(output: Any | None) -> dict | None:
    if output is None:
        return None
    planner = getattr(output, "planner_result", {}) or {}
    discovery = getattr(output, "discovery_result", {}) or {}
    policy = getattr(output, "policy_result", {}) or {}
    authorization = getattr(output, "authorization_result", {}) or {}
    legacy = getattr(output, "legacy_summary", {}) or {}
    return {
        "intent_signature": legacy.get("intent_signature", "observed"),
        "plan_signature": planner.get("plan_signature", "valid") if planner.get("hash_valid") else "invalid",
        "step_ids": tuple(planner.get("step_ids", ())),
        "tool_ids": tuple(planner.get("tool_ids", ())),
        "policy_decision": policy.get("decision"),
        "application_signature": discovery.get(
            "application_signature",
            "resolved" if discovery.get("status") == "RESOLVED" else None,
        ),
        "launch_type": discovery.get("launch_type"),
        "authorization_state": authorization.get("status"),
    }


def _safe_status(value: str) -> str:
    normalized = str(value).strip().upper()
    return (
        normalized
        if normalized
        in {
            "COMPLETED",
            "FAILED",
            "DENIED",
            "PENDING",
            "OBSERVED",
        }
        else "UNKNOWN"
    )
