"""Sanitized results and aggregate diagnostics for V2 routing."""

from dataclasses import dataclass
from datetime import datetime
from threading import RLock
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict

from sentinel.contracts._base import (
    NonEmptyString,
    require_timezone,
)


class RuntimeShadowResultV1(BaseModel):
    """Metadata-only outcome; never contains executable V2 objects."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"]
    correlation_id: NonEmptyString
    timestamp: Annotated[datetime, AfterValidator(require_timezone)]
    legacy_status: NonEmptyString
    shadow_status: NonEmptyString
    differences: tuple[NonEmptyString, ...] = ()
    warnings: tuple[NonEmptyString, ...] = ()
    errors: tuple[NonEmptyString, ...] = ()
    authority: Literal[False] = False


@dataclass(frozen=True)
class ControlledRuntimeDiagnosticsSnapshot:
    processed_events: int
    matches: int
    divergences: int
    v2_errors: int
    average_shadow_latency_ms: float
    maximum_shadow_latency_ms: float
    conversion_failures: int


class ControlledRuntimeDiagnostics:
    """Store counters and timing only, never event payloads."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._values = {
            "processed_events": 0,
            "matches": 0,
            "divergences": 0,
            "v2_errors": 0,
            "shadow_latency_total_ms": 0.0,
            "maximum_shadow_latency_ms": 0.0,
            "conversion_failures": 0,
        }

    def record(
        self,
        result: RuntimeShadowResultV1,
        *,
        latency_ms: float,
    ) -> None:
        with self._lock:
            self._values["processed_events"] += 1
            self._values["matches" if result.differences == () else "divergences"] += 1
            self._values["v2_errors"] += int(bool(result.errors))
            self._values["conversion_failures"] += sum("conversion" in value for value in result.errors)
            self._values["shadow_latency_total_ms"] += max(
                latency_ms,
                0.0,
            )
            self._values["maximum_shadow_latency_ms"] = max(
                self._values["maximum_shadow_latency_ms"],
                latency_ms,
            )

    def snapshot(self) -> ControlledRuntimeDiagnosticsSnapshot:
        with self._lock:
            count = max(int(self._values["processed_events"]), 1)
            return ControlledRuntimeDiagnosticsSnapshot(
                processed_events=int(self._values["processed_events"]),
                matches=int(self._values["matches"]),
                divergences=int(self._values["divergences"]),
                v2_errors=int(self._values["v2_errors"]),
                average_shadow_latency_ms=(self._values["shadow_latency_total_ms"] / count),
                maximum_shadow_latency_ms=self._values["maximum_shadow_latency_ms"],
                conversion_failures=int(self._values["conversion_failures"]),
            )
