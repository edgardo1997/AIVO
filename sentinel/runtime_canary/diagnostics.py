"""Sanitized input envelope and output diagnostics for runtime canary."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sentinel.contracts import IdentityContextV1, PolicyContextV1


@dataclass(frozen=True)
class RuntimeCanaryInput:
    """Ephemeral references consumed by the canary and never persisted."""

    intent: Any
    plan: Any
    application: Any
    policy: Any
    identity: IdentityContextV1 | None
    policy_context: PolicyContextV1 | None
    discovery_request: dict[str, str]
    intent_id: str
    plan_id: str


@dataclass(frozen=True)
class RuntimeCanaryResult:
    """Metadata-only result; contains no executable contract objects."""

    runtime_id: str
    timestamp: datetime
    legacy_summary: dict[str, Any]
    planner_result: dict[str, Any]
    discovery_result: dict[str, Any]
    policy_result: dict[str, Any]
    authorization_result: dict[str, Any]
    comparison_result: dict[str, Any]
    warnings: tuple[str, ...]
    schema_gaps: tuple[str, ...]
    validation_errors: tuple[str, ...]
    execution_time_ms: float

    @classmethod
    def disabled(cls, *, timestamp: datetime) -> "RuntimeCanaryResult":
        return cls(
            runtime_id="runtime_canary_disabled",
            timestamp=timestamp,
            legacy_summary={"observed": False},
            planner_result={"status": "SKIPPED"},
            discovery_result={"status": "SKIPPED"},
            policy_result={"status": "SKIPPED"},
            authorization_result={
                "status": "SKIPPED",
                "authority": False,
            },
            comparison_result={"status": "SKIPPED"},
            warnings=("runtime_canary_disabled",),
            schema_gaps=(),
            validation_errors=(),
            execution_time_ms=0.0,
        )
