"""Deep-copy router that isolates all shadow failures from legacy."""

import uuid
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Callable

from .control import RuntimeV2ActivationState, RuntimeV2Control
from .diagnostics import RuntimeShadowResultV1


ShadowHandler = Callable[[Any], RuntimeShadowResultV1]


class RuntimeV2Router:
    def __init__(self, control: RuntimeV2Control) -> None:
        self.control = control

    def route(
        self,
        legacy_event: Any,
        *,
        shadow_handler: ShadowHandler | None,
        legacy_status: str = "COMPLETED",
    ) -> RuntimeShadowResultV1:
        correlation_id = f"v2_route_{uuid.uuid4().hex}"
        timestamp = datetime.now(timezone.utc)
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
        original_snapshot = deepcopy(legacy_event)
        try:
            copied_event = deepcopy(legacy_event)
            if shadow_handler is None:
                raise ValueError("shadow handler unavailable")
            result = shadow_handler(copied_event)
            warnings = list(result.warnings)
            if legacy_event != original_snapshot:
                warnings.append("legacy_input_changed_outside_router")
            return result.model_copy(
                update={
                    "legacy_status": _safe_status(legacy_status),
                    "warnings": tuple(warnings),
                    "authority": False,
                }
            )
        except Exception:
            return RuntimeShadowResultV1(
                schema_version="1.0",
                correlation_id=correlation_id,
                timestamp=timestamp,
                legacy_status=_safe_status(legacy_status),
                shadow_status="ERROR",
                errors=("shadow_routing_failure",),
                authority=False,
            )


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
