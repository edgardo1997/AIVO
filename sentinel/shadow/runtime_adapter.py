"""Opt-in conversion facade for objects already produced by legacy runtime.

The adapter has no runtime hooks and performs no authorization or execution.
"""

from copy import deepcopy
from dataclasses import dataclass
from enum import Enum
from typing import Any
import uuid

from pydantic import ValidationError

from sentinel.adapters import (
    app_profile_to_v1,
    intent_to_v2,
    pending_action_to_v1,
    plan_to_v2,
    policy_result_to_v2,
)
from sentinel.contracts import (
    PolicyContextV1,
    ShadowExecutionTraceV1,
)
from sentinel.core.application_knowledge import AppProfile
from sentinel.core.intent import Intent
from sentinel.core.operational_memory import PendingActionRecord
from sentinel.core.planner import Plan
from sentinel.core.policy import PolicyResult

from .decision_comparison import ShadowDecisionComparison
from .event_capture import CapturedRuntimeEvent


class RuntimeShadowConversionStatus(str, Enum):
    SUCCESS = "SUCCESS"
    WARNING = "WARNING"
    ERROR = "ERROR"


@dataclass(frozen=True)
class RuntimeShadowConversion:
    component: str
    legacy_type: str
    versioned_type: str
    conversion_status: RuntimeShadowConversionStatus
    converted: Any | None
    warnings: tuple[str, ...] = ()
    validation_errors: tuple[str, ...] = ()


class RuntimeShadowAdapter:
    """Deep-copy and convert legacy values without affecting their owners."""

    def convert_intent(
        self,
        intent: Intent,
        *,
        intent_id: str | None = None,
    ) -> RuntimeShadowConversion:
        return self._convert(
            component="intent",
            legacy=intent,
            versioned_type="IntentV2",
            converter=lambda value: intent_to_v2(
                value,
                intent_id=intent_id,
            ),
        )

    def convert_plan(
        self,
        plan: Plan,
        *,
        intent_id: str,
        plan_id: str | None = None,
    ) -> RuntimeShadowConversion:
        return self._convert(
            component="planner",
            legacy=plan,
            versioned_type="ExecutionPlanV2",
            converter=lambda value: plan_to_v2(
                value,
                intent_id=intent_id,
                plan_id=plan_id,
            ),
        )

    def convert_policy(
        self,
        result: PolicyResult,
        *,
        plan_id: str,
        decision_id: str | None = None,
        policy_context: PolicyContextV1 | None = None,
    ) -> RuntimeShadowConversion:
        warnings = []
        if policy_context is None:
            warnings.append("missing_policy_context: identity and policy versions cannot be verified")
        return self._convert(
            component="policy",
            legacy=result,
            versioned_type="PolicyDecisionV2",
            warnings=warnings,
            converter=lambda value: policy_result_to_v2(
                value,
                plan_id=plan_id,
                decision_id=decision_id,
                policy_context=policy_context,
            ),
        )

    def convert_application(
        self,
        profile: AppProfile,
    ) -> RuntimeShadowConversion:
        return self._convert(
            component="application",
            legacy=profile,
            versioned_type="ApplicationDescriptorV1",
            converter=app_profile_to_v1,
        )

    def convert_pending_action(
        self,
        record: PendingActionRecord,
        *,
        intent_id: str | None = None,
        step_id: str | None = None,
        user_id: str | None = None,
    ) -> RuntimeShadowConversion:
        missing = [
            name
            for name, value in (
                ("intent_id", intent_id),
                ("step_id", step_id),
                ("user_id", user_id),
            )
            if value is None or not str(value).strip()
        ]
        if missing:
            return RuntimeShadowConversion(
                component="consent",
                legacy_type=type(record).__name__,
                versioned_type="PendingConsentV1",
                conversion_status=RuntimeShadowConversionStatus.WARNING,
                converted=None,
                warnings=tuple(f"missing_field: {field}" for field in missing),
            )
        return self._convert(
            component="consent",
            legacy=record,
            versioned_type="PendingConsentV1",
            converter=lambda value: pending_action_to_v1(
                value,
                intent_id=str(intent_id),
                step_id=str(step_id),
                user_id=str(user_id),
            ),
        )

    def convert(self, value: Any, **context: Any) -> RuntimeShadowConversion:
        if isinstance(value, Intent):
            return self.convert_intent(
                value,
                intent_id=context.get("intent_id"),
            )
        if isinstance(value, Plan):
            return self.convert_plan(
                value,
                intent_id=context.get("intent_id", ""),
                plan_id=context.get("plan_id"),
            )
        if isinstance(value, PolicyResult):
            return self.convert_policy(
                value,
                plan_id=context.get("plan_id", ""),
                decision_id=context.get("decision_id"),
                policy_context=context.get("policy_context"),
            )
        if isinstance(value, AppProfile):
            return self.convert_application(value)
        if isinstance(value, PendingActionRecord):
            return self.convert_pending_action(
                value,
                intent_id=context.get("intent_id"),
                step_id=context.get("step_id"),
                user_id=context.get("user_id"),
            )
        return RuntimeShadowConversion(
            component="unknown",
            legacy_type=type(value).__name__,
            versioned_type="UNKNOWN",
            conversion_status=RuntimeShadowConversionStatus.ERROR,
            converted=None,
            validation_errors=(f"unsupported legacy type: {type(value).__name__}",),
        )

    def convert_event(
        self,
        event: CapturedRuntimeEvent,
        *,
        legacy_model: Any | None = None,
        comparison: ShadowDecisionComparison | None = None,
        **context: Any,
    ) -> ShadowExecutionTraceV1:
        """Build a redacted trace for one captured runtime event."""
        warnings: list[str] = []
        differences: list[str] = []
        if legacy_model is None:
            conversion = RuntimeShadowConversion(
                component=event.component,
                legacy_type="runtime_event",
                versioned_type="unavailable",
                conversion_status=RuntimeShadowConversionStatus.WARNING,
                converted=None,
                warnings=("schema_gap: legacy model unavailable",),
            )
        else:
            conversion = self.convert(legacy_model, **context)
        warnings.extend(conversion.warnings)
        if conversion.validation_errors:
            warnings.append("conversion_error")
        if comparison is not None:
            warnings.extend(comparison.warnings)
            differences.extend(comparison.differences)
        return ShadowExecutionTraceV1(
            schema_version="1.0",
            trace_id=f"shadow_trace_{uuid.uuid4().hex}",
            timestamp=event.timestamp,
            component=event.component,
            legacy_type=conversion.legacy_type,
            versioned_type=conversion.versioned_type,
            conversion_status=conversion.conversion_status.value,
            warnings=tuple(_safe_diagnostics(warnings)),
            differences=tuple(_safe_diagnostics(differences)),
            correlation_ids=dict(event.correlation_ids),
        )

    def _convert(
        self,
        *,
        component: str,
        legacy: Any,
        versioned_type: str,
        converter,
        warnings: list[str] | None = None,
    ) -> RuntimeShadowConversion:
        warning_values = tuple(warnings or ())
        try:
            converted = converter(deepcopy(legacy))
            status = RuntimeShadowConversionStatus.WARNING if warning_values else RuntimeShadowConversionStatus.SUCCESS
            return RuntimeShadowConversion(
                component=component,
                legacy_type=type(legacy).__name__,
                versioned_type=versioned_type,
                conversion_status=status,
                converted=converted,
                warnings=warning_values,
            )
        except (TypeError, ValueError, ValidationError) as exc:
            return RuntimeShadowConversion(
                component=component,
                legacy_type=type(legacy).__name__,
                versioned_type=versioned_type,
                conversion_status=RuntimeShadowConversionStatus.ERROR,
                converted=None,
                warnings=warning_values,
                validation_errors=(str(exc),),
            )


def _safe_diagnostics(values: list[str]) -> list[str]:
    """Retain diagnostic categories, never arbitrary payload fragments."""
    allowed = (
        "schema_gap",
        "missing_field",
        "missing_policy_context",
        "missing_context",
        "missing_identity",
        "missing_policy_version",
        "decision_changed",
        "effect_different",
        "plan_different",
        "conversion_error",
    )
    return [value for value in values if value.startswith(allowed)]
