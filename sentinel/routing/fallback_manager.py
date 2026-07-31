import logging
import time
from typing import Any, Dict, List, Optional
from sentinel.core.router_types import TaskType, ProviderSpec, RouterDecision, FALLBACK_STRATEGIES, TOTAL_TIMEOUT_BUDGET, CALL_TIMEOUT, LOCAL_CALL_TIMEOUT, classify_provider_error, format_elapsed
from sentinel.core.circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)


class FallbackManager:
    def __init__(
        self,
        providers: Optional[Dict[str, ProviderSpec]] = None,
        default_fallback_chain: Optional[List[str]] = None,
        fallback_strategy: str = "chain",
        max_fallbacks: int = 5,
        circuit_breaker: Optional[CircuitBreaker] = None,
        fallback_stats: Optional[Dict[str, int]] = None,
        fallback_history: Optional[List[Dict[str, Any]]] = None,
    ):
        self._providers = providers or {}
        self._default_fallback_chain: List[str] = default_fallback_chain or []
        self._fallback_strategy: str = fallback_strategy if fallback_strategy in FALLBACK_STRATEGIES else "chain"
        self._max_fallbacks: int = max_fallbacks
        self._fallback_stats: Dict[str, int] = fallback_stats if fallback_stats is not None else {}
        self._fallback_history: List[Dict[str, Any]] = fallback_history if fallback_history is not None else []
        self._circuit_breaker = circuit_breaker or CircuitBreaker()
        self._failure_reporter = None

    def set_circuit_breaker(self, cb: CircuitBreaker) -> None:
        self._circuit_breaker = cb

    def set_failure_reporter(self, reporter) -> None:
        self._failure_reporter = reporter

    def set_default_fallback_chain(self, chain: List[str]) -> None:
        self._default_fallback_chain = chain

    def set_fallback_strategy(self, strategy: str) -> None:
        if strategy not in FALLBACK_STRATEGIES:
            raise ValueError(f"Fallback strategy must be one of {FALLBACK_STRATEGIES}")
        self._fallback_strategy = strategy

    def set_max_fallbacks(self, n: int) -> None:
        self._max_fallbacks = max(1, n)

    def build_fallback_chain(self, primary: RouterDecision, task_type: TaskType, context: Optional[Dict[str, Any]] = None, provider_availability_fn=None, select_all_fn=None) -> List[RouterDecision]:
        provider = self._providers.get(primary.provider_id)
        chain_ids: List[str] = []
        if provider and provider.fallback_chain:
            chain_ids = provider.fallback_chain
        elif self._default_fallback_chain:
            chain_ids = self._default_fallback_chain
        if chain_ids:
            result = [primary]
            seen = {primary.provider_id}
            for pid in chain_ids:
                if pid not in seen and pid in self._providers:
                    spec = self._providers[pid]
                    if provider_availability_fn and not provider_availability_fn(pid).available:
                        continue
                    result.append(RouterDecision(provider_id=pid, model=spec.default_model, task_type=task_type, strategy="chain", reason=f"Fallback chain: {pid}"))
                    seen.add(pid)
                if len(result) - 1 >= self._max_fallbacks:
                    break
            return result
        if select_all_fn:
            all_candidates = select_all_fn(task_type, context=context)
            result = [primary]
            seen = {primary.provider_id}
            for c in all_candidates:
                if c.provider_id not in seen:
                    result.append(c)
                    seen.add(c.provider_id)
                if len(result) - 1 >= self._max_fallbacks:
                    break
            return result
        return [primary]

    def filter_open_providers(self, candidates: List[RouterDecision]) -> List[RouterDecision]:
        filtered = []
        for c in candidates:
            if self._circuit_breaker.allow_request(c.provider_id):
                filtered.append(c)
            else:
                logger.info("Circuit breaker OPEN for %s, skipping", c.provider_id)
        return filtered

    def record_fallback(self, provider_id: str, category: str = "unknown") -> None:
        self._fallback_stats[provider_id] = self._fallback_stats.get(provider_id, 0) + 1

    def fallback_stats(self) -> Dict[str, Any]:
        return {
            "strategy": self._fallback_strategy,
            "max_fallbacks": self._max_fallbacks,
            "default_chain": list(self._default_fallback_chain),
            "fallback_counts": dict(self._fallback_stats),
            "total_fallbacks": sum(self._fallback_stats.values()),
            "recent_history": self._fallback_history[-20:],
        }

    def reset_fallback_stats(self) -> int:
        total = sum(self._fallback_stats.values())
        self._fallback_stats.clear()
        self._fallback_history.clear()
        return total

    def execute_with_fallback(self, primary_decision: RouterDecision, task_type: TaskType, messages: List[Dict[str, str]], provider_map: Dict[str, Any], call_provider_fn, model_override: Optional[str] = None, context: Optional[Dict[str, Any]] = None, fallback_chain_override: Optional[List[str]] = None, provider_availability_fn=None, select_all_fn=None) -> Dict[str, Any]:
        context = context or {}
        if fallback_chain_override is not None:
            chain = [primary_decision]
            seen = {primary_decision.provider_id}
            for pid in fallback_chain_override:
                if pid not in seen and pid in self._providers:
                    if provider_availability_fn and not provider_availability_fn(pid).available:
                        continue
                    spec = self._providers[pid]
                    chain.append(RouterDecision(provider_id=pid, model=spec.default_model, task_type=task_type, strategy=self._fallback_strategy, reason=f"Fallback override: {pid}"))
                    seen.add(pid)
                if len(chain) - 1 >= self._max_fallbacks:
                    break
        else:
            chain = self.build_fallback_chain(primary_decision, task_type, context=context, provider_availability_fn=provider_availability_fn, select_all_fn=select_all_fn)
        candidates = self.filter_open_providers(chain)
        if not candidates:
            states = self._circuit_breaker.get_all_states()
            raise RuntimeError(f"All providers unavailable (circuit breaker open) for {task_type.value}. States: {[s['provider_id'] + '=' + s['state'] for s in states]}")
        primary_id = candidates[0].provider_id
        last_error: Optional[str] = None
        start_time = time.monotonic()
        for idx, candidate in enumerate(candidates):
            provider = provider_map.get(candidate.provider_id)
            if not provider:
                continue
            elapsed = time.monotonic() - start_time
            remaining = max(5.0, TOTAL_TIMEOUT_BUDGET - elapsed)
            per_call_timeout = min(remaining, LOCAL_CALL_TIMEOUT if provider.is_local else CALL_TIMEOUT)
            try:
                result = call_provider_fn(candidate, provider, messages, model_override, timeout=per_call_timeout)
                elapsed_total = time.monotonic() - start_time
                self._circuit_breaker.record_success(candidate.provider_id)
                offline_fallback = candidate.provider_id != primary_id and getattr(self, '_offline_reason', None) is not None and provider.is_local
                result["selection"] = {
                    "primary": primary_id, "used": candidate.provider_id, "model": candidate.model,
                    "strategy": self._fallback_strategy, "reason": candidate.reason,
                    "attempt": idx + 1, "total_fallbacks_tried": idx, "elapsed": format_elapsed(elapsed_total),
                }
                if offline_fallback:
                    result["selection"]["offline_fallback"] = True
                    result["selection"]["offline_reason"] = getattr(self, '_offline_reason', None)
                    result["selection"]["fallback_explanation"] = f"Internet no disponible ({getattr(self, '_offline_reason', '')}). Usando modelo local ({candidate.provider_id}) como fallback."
                if candidate.provider_id != primary_id:
                    self.record_fallback(candidate.provider_id, "success_after_fallback")
                    self._fallback_history.append({"primary": primary_id, "used": candidate.provider_id, "model": candidate.model, "attempt": idx + 1, "elapsed": elapsed_total, "category": "success_after_fallback"})
                logger.info("Chat success: provider=%s model=%s attempt=%d/%d elapsed=%s", candidate.provider_id, candidate.model, idx + 1, len(candidates), format_elapsed(elapsed_total))
                return result
            except Exception as e:
                classification = classify_provider_error(e, candidate.provider_id)
                last_error = f"[{classification['category']}] {classification['message']}"
                self._circuit_breaker.record_failure(candidate.provider_id)
                self._fallback_history.append({"primary": primary_id, "used": candidate.provider_id, "attempt": idx + 1, "category": classification.get("category", "unknown"), "message": classification.get("message", ""), "elapsed": time.monotonic() - start_time})
                if self._failure_reporter is not None:
                    try:
                        self._failure_reporter(candidate.provider_id, candidate.model, classification)
                    except Exception as reporter_err:
                        logger.debug("Failure reporter error: %s", reporter_err)
                logger.warning("Provider %s failed (attempt %d/%d): [%s] %s", candidate.provider_id, idx + 1, len(candidates), classification["category"], classification["message"])
                if remaining < 5.0 and idx < len(candidates) - 1:
                    logger.warning("Timeout budget exhausted, stopping fallback chain")
                    break
                continue
        raise RuntimeError(f"All providers failed for {task_type.value}. Last: {last_error}. Elapsed: {format_elapsed(time.monotonic() - start_time)}")
