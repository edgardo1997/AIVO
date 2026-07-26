"""Read-only observer for legacy-to-versioned shadow conversions.

This module is opt-in and intentionally has no runtime registration. It never
executes a plan or treats a versioned contract as an authorization decision.
"""

import hashlib
import json
import threading
import uuid
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ValidationError

from sentinel.adapters import (
    app_profile_to_v1,
    intent_to_v2,
    pending_action_to_v1,
    plan_to_v2,
    policy_result_to_v2,
)
from sentinel.contracts import (
    ApplicationDescriptorV1,
    ExecutionPlanV2,
    IntentV2,
    PendingConsentV1,
    PolicyContextV1,
    PolicyDecisionV2,
    PolicyDecisionValueV2,
)
from sentinel.core.application_knowledge import AppProfile
from sentinel.core.intent import Intent
from sentinel.core.operational_memory import PendingActionRecord
from sentinel.core.planner import Plan
from sentinel.core.policy import PolicyEffect, PolicyResult

from .decision_comparison import ShadowDecisionComparison
from .runtime_adapter import (
    RuntimeShadowConversion,
    RuntimeShadowConversionStatus,
)


class ShadowMigrationGapType(str, Enum):
    MISSING_CONTRACT = "missing_contract"
    MISSING_FIELD = "missing_field"
    WARNING = "warning"


@dataclass(frozen=True)
class ShadowMigrationDiagnostic:
    """Machine-readable diagnostic emitted by a shadow comparison."""

    gap_type: ShadowMigrationGapType
    field: str
    message: str


@dataclass(frozen=True)
class ShadowMigrationResult:
    """Difference report for one non-authoritative shadow conversion."""

    migration_id: str
    timestamp: datetime
    component: str
    legacy_type: str
    versioned_type: str
    conversion_success: bool
    warnings: tuple[str, ...] = ()
    lost_fields: tuple[str, ...] = ()
    validation_errors: tuple[str, ...] = ()
    diagnostics: tuple[ShadowMigrationDiagnostic, ...] = ()
    conversion_status: str = ""
    comparison_status: str | None = None


@dataclass(frozen=True)
class ShadowMigrationMetrics:
    """Immutable snapshot of one observer's in-memory counters."""

    conversion_success: int
    conversion_failure: int
    missing_contract: int
    missing_field: int
    warning_count: int
    component_count: dict[str, int]


def _json_safe(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if hasattr(value, "to_dict"):
        return _json_safe(value.to_dict())
    if is_dataclass(value):
        return _json_safe(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return value


def _stable_id(prefix: str, value: Any) -> str:
    canonical = json.dumps(
        _json_safe(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:20]
    return f"{prefix}_shadow_{digest}"


class ShadowMigrationObserver:
    """Convert and compare contracts without influencing execution."""

    def __init__(self) -> None:
        self._results: list[ShadowMigrationResult] = []
        self._converted: dict[str, Any] = {}
        self._lock = threading.RLock()
        self._conversion_success = 0
        self._conversion_failure = 0
        self._missing_contract = 0
        self._missing_field = 0
        self._warning_count = 0
        self._component_count: dict[str, int] = {}

    def results(self) -> tuple[ShadowMigrationResult, ...]:
        with self._lock:
            return tuple(self._results)

    def get_versioned(self, migration_id: str) -> Any | None:
        """Return the internal converted value for diagnostics and tests."""
        with self._lock:
            return self._converted.get(migration_id)

    def metrics(self) -> ShadowMigrationMetrics:
        with self._lock:
            return ShadowMigrationMetrics(
                conversion_success=self._conversion_success,
                conversion_failure=self._conversion_failure,
                missing_contract=self._missing_contract,
                missing_field=self._missing_field,
                warning_count=self._warning_count,
                component_count=dict(self._component_count),
            )

    def observe_intent(self, intent: Intent) -> ShadowMigrationResult:
        intent_id = _stable_id("intent", intent)
        try:
            converted = intent_to_v2(intent, intent_id=intent_id)
            lost: list[str] = []
            warnings: list[str] = []
            if converted.parameters != intent.parameters:
                warnings.append("parameters changed during conversion")
            if converted.grounding_requirements != tuple(intent.grounding_requirements):
                lost.append("grounding_requirements")
            return self._success(
                component="intent",
                legacy=intent,
                converted=converted,
                warnings=warnings,
                lost_fields=lost,
            )
        except (TypeError, ValueError, ValidationError) as exc:
            return self._failure(
                component="intent",
                legacy=intent,
                versioned_type=IntentV2.__name__,
                error=exc,
            )

    def observe_plan(self, plan: Plan) -> ShadowMigrationResult:
        intent_id = _stable_id("intent", plan.intent)
        plan_id = _stable_id(
            "plan",
            {"intent_id": intent_id, "plan": plan},
        )
        try:
            converted = plan_to_v2(
                plan,
                intent_id=intent_id,
                plan_id=plan_id,
            )
            lost: list[str] = []
            warnings: list[str] = []
            for index, (legacy_step, versioned_step) in enumerate(zip(plan.steps, converted.steps)):
                prefix = f"steps[{index}]"
                if versioned_step.description != legacy_step.description:
                    lost.append(f"{prefix}.description")
                if versioned_step.estimated_duration_ms != legacy_step.estimated_duration_ms:
                    lost.append(f"{prefix}.estimated_duration_ms")
                expected_decision = _json_safe(legacy_step.model_decision)
                if versioned_step.model_decision != expected_decision:
                    lost.append(f"{prefix}.model_decision")
                if versioned_step.parameters != legacy_step.params:
                    warnings.append(f"{prefix}.parameters changed")
            if len(converted.steps) != len(plan.steps):
                warnings.append("step count changed during conversion")
            if lost:
                warnings.append("ExecutionStepV2 does not represent every advisory step field")
            return self._success(
                component="planner",
                legacy=plan,
                converted=converted,
                warnings=warnings,
                lost_fields=lost,
            )
        except (TypeError, ValueError, ValidationError) as exc:
            return self._failure(
                component="planner",
                legacy=plan,
                versioned_type=ExecutionPlanV2.__name__,
                error=exc,
            )

    def observe_policy(
        self,
        result: PolicyResult,
        *,
        plan_id: str | None = None,
        policy_context: PolicyContextV1 | None = None,
    ) -> ShadowMigrationResult:
        linked_plan_id = plan_id or _stable_id(
            "plan_unlinked",
            result,
        )
        decision_id = _stable_id(
            "decision",
            {"plan_id": linked_plan_id, "policy": result},
        )
        warnings = []
        if plan_id is None:
            warnings.append("plan_id was not supplied; policy-to-plan identity is not verifiable")
        if result.effect == PolicyEffect.REQUIRE_CONFIRM:
            warnings.append("legacy REQUIRE_CONFIRM maps semantically to REQUIRE_CONSENT")
        if result.context:
            warnings.append("legacy generic context is represented as risk_context")
        if policy_context is None:
            warnings.append("PolicyContextV1 was not supplied; identity and policy versions are not verifiable")
        try:
            converted = policy_result_to_v2(
                result,
                plan_id=linked_plan_id,
                decision_id=decision_id,
                timestamp=datetime.now(timezone.utc),
                policy_context=policy_context,
            )
            expected = {
                PolicyEffect.ALLOW: PolicyDecisionValueV2.ALLOW,
                PolicyEffect.REQUIRE_CONFIRM: (PolicyDecisionValueV2.REQUIRE_CONSENT),
                PolicyEffect.DENY: PolicyDecisionValueV2.DENY,
            }[result.effect]
            lost = []
            if converted.decision != expected:
                lost.append("effect")
            if converted.reason != result.reason:
                lost.append("reason")
            if converted.risk_context != result.context:
                lost.append("context")
            return self._success(
                component="policy",
                legacy=result,
                converted=converted,
                warnings=warnings,
                lost_fields=lost,
            )
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            return self._failure(
                component="policy",
                legacy=result,
                versioned_type=PolicyDecisionV2.__name__,
                error=exc,
                warnings=warnings,
            )

    def observe_application(
        self,
        profile: AppProfile,
    ) -> ShadowMigrationResult:
        warnings = [
            "legacy source is interpreted as provider",
            "source evidence is structural and not cryptographically verified",
        ]
        try:
            converted = app_profile_to_v1(profile)
            lost = []
            snapshot = converted.source_evidence[-1].get(
                "legacy_data",
                {},
            )
            for field, value in profile.to_dict().items():
                if snapshot.get(field) != value:
                    lost.append(field)
            if not any(evidence.verified for evidence in converted.resolver_evidence):
                warnings.append("ResolverEvidenceV1 is present but not verified")
            return self._success(
                component="application",
                legacy=profile,
                converted=converted,
                warnings=warnings,
                lost_fields=lost,
            )
        except (TypeError, ValueError, ValidationError) as exc:
            return self._failure(
                component="application",
                legacy=profile,
                versioned_type=ApplicationDescriptorV1.__name__,
                error=exc,
                warnings=warnings,
            )

    def observe_pending_action(
        self,
        record: PendingActionRecord,
        *,
        intent_id: str | None = None,
        step_id: str | None = None,
        user_id: str | None = None,
    ) -> ShadowMigrationResult:
        missing = [
            field
            for field, value in (
                ("intent_id", intent_id),
                ("step_id", step_id),
                ("user_id", user_id),
            )
            if value is None or not str(value).strip()
        ]
        if missing:
            diagnostics = [
                ShadowMigrationDiagnostic(
                    gap_type=ShadowMigrationGapType.MISSING_CONTRACT,
                    field="PendingActionRecord",
                    message=("The legacy record alone cannot populate a complete PendingConsentV1 contract"),
                )
            ]
            diagnostics.extend(
                ShadowMigrationDiagnostic(
                    gap_type=ShadowMigrationGapType.MISSING_FIELD,
                    field=field,
                    message=f"{field} is absent from PendingActionRecord",
                )
                for field in missing
            )
            return self._record(
                result=ShadowMigrationResult(
                    migration_id=f"migration_{uuid.uuid4().hex}",
                    timestamp=datetime.now(timezone.utc),
                    component="consent",
                    legacy_type=type(record).__name__,
                    versioned_type=PendingConsentV1.__name__,
                    conversion_success=False,
                    warnings=("PendingActionRecord must never be inferred as AuthorizationGrantV1",),
                    lost_fields=tuple(missing),
                    validation_errors=("Missing context required for PendingConsentV1",),
                    diagnostics=tuple(diagnostics),
                ),
                converted=None,
            )
        try:
            converted = pending_action_to_v1(
                record,
                intent_id=str(intent_id),
                step_id=str(step_id),
                user_id=str(user_id),
            )
            return self._success(
                component="consent",
                legacy=record,
                converted=converted,
                warnings=["PendingConsentV1 remains non-authoritative and cannot execute"],
                lost_fields=[],
            )
        except (TypeError, ValueError, ValidationError) as exc:
            return self._failure(
                component="consent",
                legacy=record,
                versioned_type=PendingConsentV1.__name__,
                error=exc,
            )

    def observe(
        self,
        value: Any,
        *,
        plan_id: str | None = None,
        policy_context: PolicyContextV1 | None = None,
        intent_id: str | None = None,
        step_id: str | None = None,
        user_id: str | None = None,
    ) -> ShadowMigrationResult:
        if isinstance(value, Intent):
            return self.observe_intent(value)
        if isinstance(value, Plan):
            return self.observe_plan(value)
        if isinstance(value, PolicyResult):
            return self.observe_policy(
                value,
                plan_id=plan_id,
                policy_context=policy_context,
            )
        if isinstance(value, AppProfile):
            return self.observe_application(value)
        if isinstance(value, PendingActionRecord):
            return self.observe_pending_action(
                value,
                intent_id=intent_id,
                step_id=step_id,
                user_id=user_id,
            )
        raise TypeError(f"unsupported shadow migration legacy type: {type(value).__name__}")

    def observe_runtime_conversion(
        self,
        conversion: RuntimeShadowConversion,
        *,
        comparison: ShadowDecisionComparison | None = None,
    ) -> ShadowMigrationResult:
        """Record an adapter result without influencing the legacy runtime."""
        diagnostics: list[ShadowMigrationDiagnostic] = []
        lost_fields: list[str] = []
        for warning in conversion.warnings:
            field = ""
            gap_type = ShadowMigrationGapType.WARNING
            if warning.startswith("missing_field:"):
                field = warning.partition(":")[2].strip()
                lost_fields.append(field)
                gap_type = ShadowMigrationGapType.MISSING_FIELD
            elif warning.startswith("missing_contract:"):
                field = warning.partition(":")[2].strip()
                gap_type = ShadowMigrationGapType.MISSING_CONTRACT
            diagnostics.append(
                ShadowMigrationDiagnostic(
                    gap_type=gap_type,
                    field=field,
                    message=warning,
                )
            )
        result = ShadowMigrationResult(
            migration_id=f"migration_{uuid.uuid4().hex}",
            timestamp=datetime.now(timezone.utc),
            component=conversion.component,
            legacy_type=conversion.legacy_type,
            versioned_type=conversion.versioned_type,
            conversion_success=(
                conversion.converted is not None
                and conversion.conversion_status is not RuntimeShadowConversionStatus.ERROR
            ),
            warnings=conversion.warnings,
            lost_fields=tuple(lost_fields),
            validation_errors=conversion.validation_errors,
            diagnostics=tuple(diagnostics),
            conversion_status=conversion.conversion_status.value,
            comparison_status=(comparison.status.value if comparison is not None else None),
        )
        return self._record(result=result, converted=conversion.converted)

    def _success(
        self,
        *,
        component: str,
        legacy: Any,
        converted: Any,
        warnings: list[str],
        lost_fields: list[str],
    ) -> ShadowMigrationResult:
        result = ShadowMigrationResult(
            migration_id=f"migration_{uuid.uuid4().hex}",
            timestamp=datetime.now(timezone.utc),
            component=component,
            legacy_type=type(legacy).__name__,
            versioned_type=type(converted).__name__,
            conversion_success=True,
            warnings=tuple(warnings),
            lost_fields=tuple(lost_fields),
            validation_errors=(),
            diagnostics=tuple(
                [
                    *(
                        ShadowMigrationDiagnostic(
                            gap_type=ShadowMigrationGapType.MISSING_FIELD,
                            field=field,
                            message=(f"{field} is not represented equivalently"),
                        )
                        for field in lost_fields
                    ),
                    *(
                        ShadowMigrationDiagnostic(
                            gap_type=ShadowMigrationGapType.WARNING,
                            field="",
                            message=warning,
                        )
                        for warning in warnings
                    ),
                ]
            ),
            conversion_status=RuntimeShadowConversionStatus.SUCCESS.value,
        )
        return self._record(result=result, converted=converted)

    def _failure(
        self,
        *,
        component: str,
        legacy: Any,
        versioned_type: str,
        error: Exception,
        warnings: list[str] | None = None,
    ) -> ShadowMigrationResult:
        if isinstance(error, ValidationError):
            errors = tuple(f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}" for item in error.errors())
        else:
            errors = (str(error),)
        return self._record(
            result=ShadowMigrationResult(
                migration_id=f"migration_{uuid.uuid4().hex}",
                timestamp=datetime.now(timezone.utc),
                component=component,
                legacy_type=type(legacy).__name__,
                versioned_type=versioned_type,
                conversion_success=False,
                warnings=tuple(warnings or ()),
                lost_fields=(),
                validation_errors=errors,
                diagnostics=tuple(
                    ShadowMigrationDiagnostic(
                        gap_type=ShadowMigrationGapType.WARNING,
                        field="",
                        message=warning,
                    )
                    for warning in (warnings or ())
                ),
                conversion_status=RuntimeShadowConversionStatus.ERROR.value,
            ),
            converted=None,
        )

    def _record(
        self,
        *,
        result: ShadowMigrationResult,
        converted: Any | None,
    ) -> ShadowMigrationResult:
        with self._lock:
            self._results.append(result)
            if result.conversion_success:
                self._conversion_success += 1
            else:
                self._conversion_failure += 1
            self._warning_count += len(result.warnings)
            self._component_count[result.component] = self._component_count.get(result.component, 0) + 1
            for diagnostic in result.diagnostics:
                if diagnostic.gap_type is ShadowMigrationGapType.MISSING_CONTRACT:
                    self._missing_contract += 1
                elif diagnostic.gap_type is ShadowMigrationGapType.MISSING_FIELD:
                    self._missing_field += 1
            if converted is not None:
                self._converted[result.migration_id] = converted
        return result
