"""Controlled replay against an injected Runtime V2 Controlled Pipeline."""

import hashlib
import json
import time
import uuid
from datetime import datetime, timezone
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict

from sentinel.contracts._base import (
    NonEmptyString,
    require_timezone,
)

from .comparison import (
    ReplayComparisonStatus,
    ReplayComponentSignature,
    compare_signatures,
)
from .control import ReplayValidationControl
from .dataset import ReplayDatasetV1
from .metrics import ReplayMetrics


class ReplayExecutionResultV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"]
    replay_id: NonEmptyString
    event_id: NonEmptyString
    timestamp: Annotated[datetime, AfterValidator(require_timezone)]
    shadow_status: NonEmptyString
    comparison_result: ReplayComparisonStatus
    warnings: tuple[NonEmptyString, ...] = ()
    errors: tuple[NonEmptyString, ...] = ()
    execution_time_ms: float
    authority: Literal[False] = False


class RuntimeReplayRunner:
    """Replay hash-only events; output diagnostics have no authority."""

    def __init__(
        self,
        *,
        control: ReplayValidationControl,
        controlled_pipeline: Any,
        metrics: ReplayMetrics | None = None,
        historical_baselines: (dict[str, ReplayComponentSignature] | None) = None,
    ) -> None:
        self.control = control
        self._pipeline = controlled_pipeline
        self.metrics = metrics or ReplayMetrics()
        self._baselines = dict(historical_baselines or {})

    def replay(
        self,
        dataset: ReplayDatasetV1,
        *,
        repetitions: int = 1,
    ) -> tuple[ReplayExecutionResultV1, ...]:
        if repetitions < 1:
            raise ValueError("repetitions must be positive")
        if not self.control.begin():
            return ()
        results: list[ReplayExecutionResultV1] = []
        first_signature = None
        try:
            for index in range(repetitions):
                started = time.perf_counter()
                try:
                    controlled_result = self._pipeline.observe(
                        {
                            "event_id": dataset.event_id,
                            "event_type": dataset.event_type,
                            "version": dataset.version,
                            "sanitized_payload_hash": (dataset.sanitized_payload_hash),
                            "timestamp": dataset.timestamp.isoformat(),
                        },
                        legacy_status="OBSERVED",
                        legacy_comparison=_legacy_comparison(dataset),
                    )
                except Exception:
                    controlled_result = None
                if controlled_result is None:
                    comparison = ReplayComparisonStatus.UNKNOWN
                else:
                    signature = _signature(dataset, controlled_result)
                    if index == 0:
                        baseline = self._baselines.get(dataset.event_id)
                        comparison = (
                            compare_signatures(
                                baseline,
                                signature,
                                repeated_execution=False,
                            )
                            if baseline is not None
                            else ReplayComparisonStatus.MATCH
                        )
                        first_signature = signature
                    else:
                        comparison = compare_signatures(
                            first_signature,
                            signature,
                            repeated_execution=True,
                        )
                elapsed_ms = (time.perf_counter() - started) * 1000
                warnings = _safe_codes(
                    getattr(controlled_result, "warnings", ()) if controlled_result is not None else (),
                    fallback="shadow_warning",
                )
                errors = _safe_codes(
                    getattr(controlled_result, "errors", ())
                    if controlled_result is not None
                    else ("shadow_pipeline_failure",),
                    fallback="shadow_error",
                )
                result = ReplayExecutionResultV1(
                    schema_version="1.0",
                    replay_id=f"replay_{uuid.uuid4().hex}",
                    event_id=dataset.event_id,
                    timestamp=datetime.now(timezone.utc),
                    shadow_status=_safe_status(
                        getattr(
                            controlled_result,
                            "shadow_status",
                            "ERROR",
                        )
                        if controlled_result is not None
                        else "ERROR"
                    ),
                    comparison_result=comparison,
                    warnings=warnings,
                    errors=errors,
                    execution_time_ms=elapsed_ms,
                    authority=False,
                )
                results.append(result)
                self.metrics.record(
                    comparison=comparison,
                    has_errors=bool(errors),
                    latency_ms=elapsed_ms,
                )
        finally:
            self.control.finish()
        return tuple(results)


def _legacy_comparison(dataset: ReplayDatasetV1) -> dict:
    digest = dataset.sanitized_payload_hash
    return {
        "intent_signature": digest,
        "plan_signature": _hash("plan", digest),
        "step_ids": (),
        "tool_ids": (),
        "policy_decision": _hash("policy", digest),
        "application_signature": _hash("discovery", digest),
        "launch_type": "sanitized",
        "authorization_state": _hash("authorization", digest),
    }


def _signature(
    dataset: ReplayDatasetV1,
    controlled_result: Any,
) -> ReplayComponentSignature:
    differences = tuple(getattr(controlled_result, "differences", ()))
    base = {
        "status": getattr(controlled_result, "shadow_status", "UNKNOWN"),
        "differences": differences,
    }
    return ReplayComponentSignature(
        intent_hash=dataset.sanitized_payload_hash,
        plan_hash=_hash("plan", _subset(base, "PLAN")),
        policy_decision_hash=_hash("policy", _subset(base, "POLICY")),
        discovery_metadata_hash=_hash(
            "discovery",
            _subset(base, "DISCOVERY"),
        ),
        authorization_metadata_hash=_hash(
            "authorization",
            _subset(base, "AUTHORIZATION"),
        ),
    )


def _subset(base: dict, category: str) -> str:
    payload = {
        "status": base["status"],
        "differences": [value for value in base["differences"] if category in str(value).upper()],
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _hash(label: str, value: str) -> str:
    return hashlib.sha256(f"{label}:{value}".encode("utf-8")).hexdigest()


def _safe_codes(values, *, fallback: str) -> tuple[str, ...]:
    allowed = {
        "shadow_pipeline_failure",
        "shadow_pipeline_unavailable",
        "shadow_routing_failure",
        "v2_routing_disabled",
        "shadow_result_unavailable",
    }
    return tuple(str(value) if str(value) in allowed else fallback for value in values)


def _safe_status(value: str) -> str:
    normalized = str(value).strip().upper()
    return (
        normalized
        if normalized
        in {
            "OBSERVED",
            "ERROR",
            "DISABLED",
            "UNKNOWN",
        }
        else "UNKNOWN"
    )
