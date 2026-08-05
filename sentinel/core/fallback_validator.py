"""Revalidation logic for model routing fallback candidates."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sentinel.core.model_schemas import CapabilityStatus, ModelCandidate, ModelRequest, ProviderState, RoutingDecision, SelectionReasonCode
from sentinel.core.model_errors import RoutingError, RoutingErrorCode
from sentinel.core.router_types import BUILTIN_PROVIDERS
from sentinel.security.cloud_authority import CloudAuthorizationError


class FallbackValidator:
    """Revalidates every fallback candidate from first principles."""

    def __init__(self, provider_manager, budget_manager, circuit_breaker):
        self._provider_manager = provider_manager
        self._budget_manager = budget_manager
        self._circuit_breaker = circuit_breaker

    def revalidate(
        self,
        request: ModelRequest,
        candidate: ModelCandidate,
        messages: List[Dict[str, str]],
        context_tokens: int,
    ) -> RoutingDecision:
        """Return a validated decision or raise RoutingError."""
        # 1. Provider configured and enabled
        state = self._provider_manager.get_provider_state(candidate.provider_id)
        if state["state"] == ProviderState.NOT_INSTALLED:
            raise RoutingError(
                RoutingErrorCode.PROVIDER_NOT_CONFIGURED,
                f"Provider {candidate.provider_id} is not configured.",
                retryable=False,
            )
        if state["state"] == ProviderState.DISABLED:
            raise RoutingError(
                RoutingErrorCode.PROVIDER_DISABLED,
                f"Provider {candidate.provider_id} is disabled.",
                retryable=False,
            )

        # 2. Health / readiness
        if not state.get("inference_ready", candidate.healthy):
            if self._circuit_breaker and not self._circuit_breaker.allow_request(candidate.provider_id):
                raise RoutingError(
                    RoutingErrorCode.PROVIDER_CIRCUIT_OPEN,
                    f"Provider {candidate.provider_id} circuit is open.",
                    retryable=True,
                    recommended_action="wait_and_retry",
                )
            if not candidate.healthy:
                raise RoutingError(
                    RoutingErrorCode.PROVIDER_UNAVAILABLE,
                    f"Provider {candidate.provider_id} is not available.",
                    retryable=True,
                )

        # 3. Local-only
        if request.local_only and not candidate.is_local:
            raise RoutingError(
                RoutingErrorCode.MODEL_CLOUD_NOT_AUTHORIZED,
                "Local-only request cannot use cloud provider.",
                retryable=False,
            )

        # 4. Cloud authority
        from sentinel.core.router_types import ProviderSpec
        spec = next((p for p in BUILTIN_PROVIDERS if p.id == candidate.provider_id), None)
        provider_spec = spec or ProviderSpec(id=candidate.provider_id, name=candidate.provider_id, task_types=[], is_local=False)
        if not candidate.is_local:
            if not request.cloud_allowed:
                raise RoutingError(
                    RoutingErrorCode.MODEL_CLOUD_NOT_AUTHORIZED,
                    "Request does not allow cloud execution.",
                    retryable=False,
                    recommended_action="request_cloud_authorization",
                )
            if self._provider_manager._cloud_authority is not None:
                try:
                    self._provider_manager._assert_cloud_authorized(
                        provider_spec,
                        candidate.model_id,
                    )
                except CloudAuthorizationError as exc:
                    raise RoutingError(
                        RoutingErrorCode.MODEL_CLOUD_NOT_AUTHORIZED,
                        str(exc),
                        retryable=False,
                        recommended_action="request_cloud_authorization",
                    ) from exc

        # 5. Capabilities
        for cap in request.required_capabilities:
            found = next((c for c in candidate.capabilities if c.name == cap), None)
            if not found or found.status in (CapabilityStatus.UNKNOWN, CapabilityStatus.UNSUPPORTED):
                raise RoutingError(
                    RoutingErrorCode.MODEL_CAPABILITY_MISMATCH,
                    f"Required capability {cap} not verified for {candidate.model_id}.",
                    retryable=False,
                )

        # 6. Context window (revalidate on current tokens)
        # Simplified: allow if status declared/verified
        if any(c.name == "long_context" for c in request.required_capabilities):
            if not any(c.name == "long_context" for c in candidate.capabilities if c.status != CapabilityStatus.UNKNOWN):
                raise RoutingError(
                    RoutingErrorCode.MODEL_CONTEXT_EXCEEDED,
                    f"Long context capability not verified for {candidate.model_id}.",
                    retryable=False,
                )

        # 7. Budget reservation
        from sentinel.core.cost_tracker import MODEL_PRICING
        by_provider = MODEL_PRICING.get(candidate.provider_id, {})
        per_1k = by_provider.get(candidate.model_id, by_provider.get("default", 0.0))
        estimate = (context_tokens / 1000.0) * per_1k
        if not self._budget_manager.reserve(candidate.provider_id, candidate.model_id, estimate):
            raise RoutingError(
                RoutingErrorCode.MODEL_BUDGET_EXCEEDED,
                f"Budget exceeded for fallback candidate {candidate.model_id}.",
                retryable=False,
                recommended_action="reduce_scope_or_increase_budget",
            )

        return RoutingDecision(
            selected_provider=candidate.provider_id,
            selected_model=candidate.model_id,
            selection_reason_code=SelectionReasonCode.CLOUD_AUTHORIZED_LOCAL_INSUFFICIENT,
            candidate_count=1,
            matched_capabilities=request.required_capabilities,
            missing_capabilities=[],
            cloud_used=not candidate.is_local,
            authority_reference=request.cloud_authority_reference,
            estimated_cost=estimate,
            estimated_latency_ms=0,
            fallback_chain=[],
            confidence="medium",
            candidates=[candidate],
            safe_explanation=f"Fallback validated {candidate.model_id} from {candidate.provider_id}.",
        )
