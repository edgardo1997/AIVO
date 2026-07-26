"""Completely parallel, non-authoritative V2 runtime canary pipeline."""

import time
import uuid
from copy import deepcopy
from datetime import datetime, timezone

from sentinel.application_discovery_v2 import (
    ApplicationResolverV2,
    ApplicationShadowComparison,
)
from sentinel.authorization_canary import AuthorizationCanaryService
from sentinel.policy_v2_shadow import (
    PolicyEngineV2Shadow,
    PolicyRuleAdapter,
    PolicyShadowComparison,
)
from sentinel.shadow import (
    RuntimeShadowAdapter,
    RuntimeShadowConversionStatus,
)

from .comparison import RuntimeCanaryComparison
from .control import runtime_canary_enabled
from .diagnostics import RuntimeCanaryInput, RuntimeCanaryResult
from .metrics import RuntimeCanaryMetrics


class RuntimeCanaryPipeline:
    """Observe a deep-copied legacy snapshot and return safe summaries."""

    def __init__(
        self,
        *,
        application_resolver: ApplicationResolverV2,
        enabled: bool | None = None,
        metrics: RuntimeCanaryMetrics | None = None,
    ) -> None:
        self._enabled = runtime_canary_enabled() if enabled is None else enabled
        self._resolver = application_resolver
        self.metrics = metrics or RuntimeCanaryMetrics()
        self._adapter = RuntimeShadowAdapter()

    @property
    def enabled(self) -> bool:
        return self._enabled

    def observe(
        self,
        snapshot: RuntimeCanaryInput,
    ) -> RuntimeCanaryResult:
        timestamp = datetime.now(timezone.utc)
        if not self._enabled:
            return RuntimeCanaryResult.disabled(timestamp=timestamp)
        started = time.perf_counter()
        data = deepcopy(snapshot)
        warnings: list[str] = []
        schema_gaps: list[str] = []
        errors: list[str] = []

        intent_conversion = self._adapter.convert_intent(
            data.intent,
            intent_id=data.intent_id,
        )
        plan_conversion = self._adapter.convert_plan(
            data.plan,
            intent_id=data.intent_id,
            plan_id=data.plan_id,
        )
        _collect_conversion(
            intent_conversion,
            warnings=warnings,
            schema_gaps=schema_gaps,
            errors=errors,
        )
        _collect_conversion(
            plan_conversion,
            warnings=warnings,
            schema_gaps=schema_gaps,
            errors=errors,
        )

        legacy_application = self._adapter.convert_application(data.application)
        _collect_conversion(
            legacy_application,
            warnings=warnings,
            schema_gaps=schema_gaps,
            errors=errors,
        )
        discovered = None
        application_comparison = None
        try:
            discovered = self._resolver.resolve(data.discovery_request)
            application_comparison = ApplicationShadowComparison.compare(
                data.application,
                discovered,
            )
        except (LookupError, TypeError, ValueError) as exc:
            errors.append(_error_code("discovery", exc))

        policy_evaluation = None
        policy_comparison = None
        if discovered is not None and plan_conversion.converted is not None and intent_conversion.converted is not None:
            try:
                rules = PolicyRuleAdapter.adapt(
                    data.policy,
                    version=_policy_version(data.policy_context),
                )
                policy_evaluation = PolicyEngineV2Shadow(enabled=True).evaluate(
                    intent=intent_conversion.converted,
                    plan=plan_conversion.converted,
                    identity=data.identity,
                    policy_context=data.policy_context,
                    application=discovered,
                    rules=rules,
                )
                warnings.extend(policy_evaluation.warnings)
                if policy_evaluation.decision is not None:
                    policy_comparison = PolicyShadowComparison.compare(
                        legacy=data.policy,
                        shadow=policy_evaluation.decision,
                    )
            except (TypeError, ValueError) as exc:
                errors.append(_error_code("policy", exc))

        authorization_valid = False
        authorization_summary = {
            "status": "NOT_GENERATED",
            "authority": False,
            "single_use": True,
        }
        if (
            policy_evaluation is not None
            and policy_evaluation.decision is not None
            and data.identity is not None
            and plan_conversion.converted is not None
            and plan_conversion.converted.steps
        ):
            canary = AuthorizationCanaryService(enabled=True)
            try:
                grant = canary.create_grant(
                    policy_decision=policy_evaluation.decision,
                    identity=data.identity,
                    plan=plan_conversion.converted,
                    step=plan_conversion.converted.steps[0],
                )
                if grant is not None:
                    canary.validate(
                        grant,
                        policy_decision=policy_evaluation.decision,
                        identity=data.identity,
                        plan=plan_conversion.converted,
                        step=plan_conversion.converted.steps[0],
                    )
                    authorization_valid = True
                    authorization_summary = {
                        "status": "VALIDATED_SIMULATION",
                        "authority": False,
                        "single_use": grant.single_use,
                    }
            except (PermissionError, TypeError, ValueError) as exc:
                warnings.append(_error_code("authorization", exc))

        comparison = RuntimeCanaryComparison.build(
            planner_ok=(plan_conversion.conversion_status is not RuntimeShadowConversionStatus.ERROR),
            application_comparison=application_comparison,
            policy_comparison=policy_comparison,
            authorization_valid=authorization_valid,
            identity_warnings=tuple(item for item in warnings if "identity" in item or "context" in item),
            schema_gaps=tuple(schema_gaps),
        )
        elapsed_ms = (time.perf_counter() - started) * 1000
        result = RuntimeCanaryResult(
            runtime_id=f"runtime_canary_{uuid.uuid4().hex}",
            timestamp=timestamp,
            legacy_summary={
                "observed": True,
                "intent_type": type(snapshot.intent).__name__,
                "plan_type": type(snapshot.plan).__name__,
                "application_type": type(snapshot.application).__name__,
                "policy_type": type(snapshot.policy).__name__,
            },
            planner_result={
                "status": plan_conversion.conversion_status.value,
                "step_count": (len(plan_conversion.converted.steps) if plan_conversion.converted is not None else 0),
                "hash_valid": plan_conversion.converted is not None,
            },
            discovery_result={
                "status": ("RESOLVED" if discovered is not None else "FAILED"),
                "provider": (discovered.provider if discovered is not None else None),
                "launch_type": (discovered.launch_type.value if discovered is not None else None),
                "evidence_present": bool(discovered and discovered.resolver_evidence),
            },
            policy_result={
                "status": ("EVALUATED" if policy_evaluation is not None else "FAILED"),
                "decision": (
                    policy_evaluation.decision.decision.value
                    if policy_evaluation is not None and policy_evaluation.decision is not None
                    else None
                ),
                "policy_count": (len(policy_evaluation.evaluated_policies) if policy_evaluation is not None else 0),
            },
            authorization_result=authorization_summary,
            comparison_result=comparison.summary(),
            warnings=tuple(dict.fromkeys([*warnings, *comparison.warnings])),
            schema_gaps=tuple(dict.fromkeys(schema_gaps)),
            validation_errors=tuple(dict.fromkeys(errors)),
            execution_time_ms=elapsed_ms,
        )
        self.metrics.record(result)
        return result


def _collect_conversion(
    conversion,
    *,
    warnings: list[str],
    schema_gaps: list[str],
    errors: list[str],
) -> None:
    warnings.extend(conversion.warnings)
    for warning in conversion.warnings:
        if warning.startswith(("missing_field", "schema_gap")):
            schema_gaps.append(warning)
    if conversion.validation_errors:
        errors.append(f"{conversion.component}_conversion_failed")


def _policy_version(policy_context) -> str:
    if policy_context is None:
        return "unknown"
    versions = tuple(policy_context.evaluated_policy_versions.values())
    return versions[0] if versions else "unknown"


def _error_code(stage: str, _error: Exception) -> str:
    return f"{stage}_validation_failed"
