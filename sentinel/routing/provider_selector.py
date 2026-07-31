import logging
import time
from typing import Any, Callable, Dict, List, Optional
from sentinel.core.router_types import TaskType, ProviderSpec, RouterDecision, ProviderAvailability, ROUTING_STRATEGIES, OFFLINE_MODES
from sentinel.core.hardware_intelligence import HardwareProfile, ModelCapabilityManager, get_model_capabilities
from sentinel.core.model_registry import ModelRegistry, TASK_CAPABILITY_MAP
from sentinel.core.circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)


class ProviderSelector:
    def __init__(
        self,
        providers: Optional[Dict[str, ProviderSpec]] = None,
        strategy: str = "priority",
        preferred_provider: Optional[str] = None,
        capability_manager: Optional[ModelCapabilityManager] = None,
        availability_checker: Optional[Callable[[ProviderSpec], ProviderAvailability]] = None,
        availability_ttl_seconds: float = 15.0,
    ):
        self._providers = providers or {}
        self._strategy = strategy
        self._preferred_provider = preferred_provider
        self._capability_manager = capability_manager or get_model_capabilities()
        self._availability_checker = availability_checker
        self._availability_ttl_seconds = max(0.0, availability_ttl_seconds)
        self._availability_cache: Dict[str, ProviderAvailability] = {}
        self._task_capability_map: Dict[TaskType, List[str]] = {}
        self._model_registry: Optional[ModelRegistry] = None
        self._feedback_store: Any = None
        self._cost_tracker: Any = None
        self._offline_mode: str = "auto"
        self._offline_reason: Optional[str] = None
        self._health_checker: Any = None
        self._routing_history: List[Dict[str, Any]] = []
        self._key_map: Dict[str, str] = {}
        self._ranking: Any = None

    def set_api_key(self, provider_id: str, key: str) -> None:
        self._key_map[provider_id] = key

    def delete_api_key(self, provider_id: str) -> bool:
        return bool(self._key_map.pop(provider_id, None))

    def set_model_registry(self, registry: ModelRegistry) -> None:
        self._model_registry = registry

    def set_feedback_store(self, store: Any) -> None:
        self._feedback_store = store

    def set_cost_tracker(self, tracker: Any) -> None:
        self._cost_tracker = tracker

    def set_strategy(self, strategy: str) -> None:
        if strategy not in ROUTING_STRATEGIES:
            raise ValueError(f"Strategy must be one of {ROUTING_STRATEGIES}")
        self._strategy = strategy

    def set_preferred_provider(self, provider_id: Optional[str]) -> None:
        if provider_id and provider_id not in self._providers:
            raise KeyError(f"Provider '{provider_id}' not found")
        self._preferred_provider = provider_id or None

    def set_offline_mode(self, mode: str) -> None:
        if mode not in OFFLINE_MODES:
            raise ValueError(f"offline_mode must be one of {OFFLINE_MODES}")
        self._offline_mode = mode
        if mode == "force_local":
            self._offline_reason = "offline_mode_forced"
        else:
            self._offline_reason = None

    def set_health_checker(self, checker) -> None:
        self._health_checker = checker

    def set_ranking_engine(self, ranking: Any) -> None:
        self._ranking = ranking

    def get_offline_mode(self) -> str:
        return self._offline_mode

    def is_offline(self) -> bool:
        if self._offline_mode == "force_local":
            self._offline_reason = "offline_mode_forced"
            return True
        if self._offline_mode == "off":
            self._offline_reason = None
            return False
        if self._health_checker is not None:
            offline = not self._health_checker.internet_online
            self._offline_reason = "no_internet" if offline else None
            return offline
        return False

    def set_task_capability_map(self, mapping: Dict[TaskType, List[str]]) -> None:
        self._task_capability_map = mapping

    def provider_availability(self, provider_id: str, refresh: bool = False) -> ProviderAvailability:
        if not refresh and provider_id in self._availability_cache:
            cached = self._availability_cache[provider_id]
            if time.monotonic() - cached.checked_at < self._availability_ttl_seconds:
                return cached
        provider = self._providers.get(provider_id)
        if not provider:
            result = ProviderAvailability(provider_id=provider_id, available=False, reason="unknown_provider", checked_at=time.monotonic())
            self._availability_cache[provider_id] = result
            return result
        if provider.requires_key and not self._has_api_key(provider_id):
            result = ProviderAvailability(provider_id=provider_id, available=False, reason="missing_api_key", checked_at=time.monotonic())
            self._availability_cache[provider_id] = result
            return result
        if provider.is_local:
            if self._availability_checker:
                try:
                    result = self._availability_checker(provider)
                    self._availability_cache[provider_id] = result
                    return result
                except Exception as e:
                    logger.debug("Availability check failed for %s: %s", provider_id, e)
            result = ProviderAvailability(provider_id=provider_id, available=True, reason="available", checked_at=time.monotonic())
            self._availability_cache[provider_id] = result
            return result
        result = ProviderAvailability(provider_id=provider_id, available=True, reason="api_key_configured", checked_at=time.monotonic())
        self._availability_cache[provider_id] = result
        return result

    def _has_api_key(self, provider_id: str) -> bool:
        if provider_id in self._key_map:
            return bool(self._key_map[provider_id])
        return False

    def availability_snapshot(self, refresh: bool = False) -> Dict[str, Dict[str, Any]]:
        return {
            pid: self.provider_availability(pid, refresh=refresh).to_dict()
            for pid in self._providers
        }

    def select(self, task_type: TaskType, context: Optional[Dict[str, Any]] = None) -> RouterDecision:
        if self._strategy == "smart":
            return self._smart_select(task_type, context or {})
        candidates = self._filter_candidates(task_type, context)
        if not candidates:
            registry_decision = self._try_select_from_registry(task_type, context)
            if registry_decision is not None:
                return registry_decision
            snapshot = {
                p.id: self._candidate_exclusion_reason(p, context)
                for p in self._providers.values()
                if task_type in p.task_types
            }
            raise RuntimeError(f"No available provider supports task type '{task_type.value}'. Exclusions: {snapshot}")
        if self._preferred_provider:
            candidates.sort(key=lambda p: (p.id != self._preferred_provider, -p.priority))
        elif self._strategy == "local_first":
            candidates.sort(key=lambda p: (not p.is_local, -p.priority))
        elif self._strategy == "cost":
            candidates.sort(key=lambda p: (p.requires_key, -p.priority))
        else:
            candidates.sort(key=lambda p: -p.priority)
        best = candidates[0]
        excluded = {p.id: self._candidate_exclusion_reason(p, context) for p in self._providers.values() if task_type in p.task_types and p.id not in {c.id for c in candidates}}
        hardware = self._hardware_trace(candidates, context)
        reason = f"Selected {best.id} for {task_type.value} (strategy={self._strategy}, priority={best.priority}, availability=verified)"
        if self._offline_reason:
            reason += f", offline={self._offline_reason}"
        logger.info(reason)
        return RouterDecision(
            provider_id=best.id, model=best.default_model, task_type=task_type,
            strategy=self._strategy, reason=reason,
            selection_trace={"eligible": [p.id for p in candidates], "excluded": excluded, "hardware": hardware, "offline_reason": self._offline_reason},
        )

    def _filter_candidates(self, task_type: TaskType, context: Optional[Dict[str, Any]] = None) -> List[ProviderSpec]:
        offline = self.is_offline()
        return [
            p for p in self._providers.values()
            if task_type in p.task_types
            and self.provider_availability(p.id).available
            and self._hardware_allows(p, context)
            and (not offline or p.is_local)
        ]

    def _hardware_allows(self, provider: ProviderSpec, context: Optional[Dict[str, Any]]) -> bool:
        assessment = self._hardware_assessment(provider, context)
        return not assessment or assessment.get("compatible") is not False

    def _hardware_assessment(self, provider: ProviderSpec, context: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not provider.is_local:
            return None
        profile = self._hardware_profile(context)
        if profile is None:
            return None
        return self._capability_manager.assess(provider.default_model, profile, provider.config).to_dict()

    @staticmethod
    def _hardware_profile(context: Optional[Dict[str, Any]]) -> Optional[HardwareProfile]:
        if not context:
            return None
        hardware = context.get("hardware")
        if not isinstance(hardware, dict):
            deep = context.get("deep_context")
            hardware = deep.get("hardware") if isinstance(deep, dict) else None
        return HardwareProfile.from_context(hardware) if isinstance(hardware, dict) else None

    def _candidate_exclusion_reason(self, provider: ProviderSpec, context: Optional[Dict[str, Any]]) -> str:
        availability = self.provider_availability(provider.id)
        if not availability.available:
            return availability.reason
        assessment = self._hardware_assessment(provider, context)
        if assessment and assessment.get("compatible") is False:
            return f"hardware_incompatible: {assessment.get('reason')}"
        return "not_eligible"

    def _hardware_trace(self, candidates: List[ProviderSpec], context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        return {
            p.id: assessment for p in candidates
            if (assessment := self._hardware_assessment(p, context)) is not None
        }

    def _smart_select(self, task_type: TaskType, context: Dict[str, Any]) -> RouterDecision:
        candidates = self._filter_candidates(task_type, context)
        if not candidates:
            exclusions = {p.id: self._candidate_exclusion_reason(p, context) for p in self._providers.values() if task_type in p.task_types}
            raise RuntimeError(f"No available provider supports task type '{task_type.value}'. Exclusions: {exclusions}")
        sys_sum = context.get("system_summary", {}) or {}
        cpu = sys_sum.get("cpu_percent", 50)
        mem = sys_sum.get("memory_percent", 50)
        perm_level = context.get("permission_level", "confirm")
        battery = sys_sum.get("battery", None)
        is_high_load = (isinstance(cpu, (int, float)) and cpu > 80) or (isinstance(mem, (int, float)) and mem > 85)
        is_battery_low = isinstance(battery, dict) and battery.get("percent", 100) < 20 and not battery.get("power_plugged", True)
        is_restricted = perm_level in ("emergency", "restricted")
        prefers_local_for_privacy = perm_level in ("high", "emergency")

        def dynamic_score(p: ProviderSpec) -> float:
            score = float(p.priority)
            if self._preferred_provider and p.id == self._preferred_provider:
                score += 60
            if task_type in (TaskType.LOCAL, TaskType.QUICK) and p.is_local:
                score += 20
            if task_type in (TaskType.REASONING, TaskType.ANALYSIS, TaskType.CODE) and not p.is_local:
                score += 10
            if is_high_load and not p.is_local:
                score += 15
            if is_high_load and p.is_local:
                score -= 10
            if is_battery_low and not p.is_local:
                score += 10
            if is_battery_low and p.is_local:
                score -= 5
            if is_restricted:
                score += 5
            if prefers_local_for_privacy and p.is_local:
                score += 15
            if prefers_local_for_privacy and not p.is_local:
                score -= 5
            if self._feedback_store is not None:
                success_rate = self._feedback_store.get_success_rate(p.id, task_type)
                avg_dur = self._feedback_store.get_avg_duration(p.id, task_type)
                if success_rate > 0:
                    score += success_rate * 20
                if success_rate == 0 and self._feedback_store.total_records > 0:
                    stat = [s for s in self._feedback_store.get_stats(p.id, task_type) if s.total > 0]
                    if not stat:
                        score -= 5
                    else:
                        score -= (1.0 - success_rate) * 10
                if avg_dur is not None and avg_dur < 1000:
                    score += 5
                elif avg_dur is not None and avg_dur > 10000:
                    score -= 5
            if self._cost_tracker is not None:
                cost = self._cost_tracker.get_model_price(p.id, p.default_model)
                if cost > 0:
                    score -= cost * 1000
            if self._ranking is not None:
                bonus = self._model_ranking_bonus(p, task_type)
                score += bonus
            return score

        candidates.sort(key=dynamic_score, reverse=True)
        best = candidates[0]
        factors = f"cpu={cpu}% mem={mem}% perm={perm_level}"
        if battery:
            factors += f" battery={battery.get('percent', '?')}% plugged={battery.get('power_plugged', '?')}"
        if self._feedback_store is not None:
            sr = self._feedback_store.get_success_rate(best.id, task_type)
            factors += f" feedback_sr={sr:.0%}"
        if self._cost_tracker is not None:
            cost = self._cost_tracker.get_model_price(best.id, best.default_model)
            factors += f" cost_usd_per_1k=${cost:.6f}"
        if self._ranking is not None:
            rscores = self._ranking.compute_scores(model_ids=[best.id])
            if rscores:
                factors += f" ranking_score={rscores[0].performance_score:.1f}"
        reason = f"Smart-selected {best.id} for {task_type.value} (score={dynamic_score(best):.0f}, {factors})"
        logger.debug(reason)
        return RouterDecision(
            provider_id=best.id, model=best.default_model, task_type=task_type,
            strategy="smart", reason=reason,
            selection_trace={"eligible": [p.id for p in candidates], "score": dynamic_score(best), "hardware": self._hardware_trace(candidates, context)},
        )

    def _model_ranking_bonus(self, provider: ProviderSpec, task_type: TaskType) -> float:
        """Bonus de ranking basado en el mejor modelo real del proveedor.

        Usa el ModelRegistry para mapear proveedor → modelos registrados
        y el ModelRanking para ordenarlos por rendimiento observado.
        """
        if self._ranking is None:
            return 0.0
        try:
            model_ids = self._registry_model_ids(provider)
            if not model_ids:
                return 0.0
            scores = self._ranking.get_top_k(k=10)
            if not scores:
                return 0.0
            score_by_id = {s.model_id: s for s in scores}
            best = None
            for mid in model_ids:
                s = score_by_id.get(mid)
                if s is not None:
                    if best is None or s.performance_score > best.performance_score:
                        best = s
            if best is not None:
                return best.performance_score * 0.3
        except Exception as e:
            logger.debug("Ranking bonus failed for %s: %s", provider.id, e)
        return 0.0

    def _registry_model_ids(self, provider: ProviderSpec) -> List[str]:
        if self._model_registry is None:
            return []
        try:
            models = self._model_registry.find_by_provider(provider.id)
            return [m.id for m in models if m.status.name == "AVAILABLE"] or [provider.default_model]
        except Exception:
            return [provider.default_model] if provider.default_model else []

    def select_all(self, task_type: TaskType, context: Optional[Dict[str, Any]] = None) -> List[RouterDecision]:
        candidates = self._filter_candidates(task_type, context)
        if self._strategy == "smart":
            ctx = context or {}
            sys_sum = ctx.get("system_summary", {}) or {}
            cpu = sys_sum.get("cpu_percent", 50)
            mem = sys_sum.get("memory_percent", 50)
            is_high_load = (isinstance(cpu, (int, float)) and cpu > 80) or (isinstance(mem, (int, float)) and mem > 85)
            candidates.sort(key=lambda p: (float(p.priority) + (10 if is_high_load and not p.is_local else (-5 if is_high_load and p.is_local else 0))), reverse=True)
        elif self._strategy == "local_first":
            candidates.sort(key=lambda p: (not p.is_local, -p.priority))
        elif self._strategy == "cost":
            candidates.sort(key=lambda p: (p.requires_key, -p.priority))
        else:
            candidates.sort(key=lambda p: -p.priority)
        return [
            RouterDecision(provider_id=p.id, model=p.default_model, task_type=task_type, strategy=self._strategy, reason=f"Candidate {p.id} (priority={p.priority})")
            for p in candidates
        ]

    def select_by_capability(self, required_capabilities: List[str], task_type: Optional[TaskType] = None, context: Optional[Dict[str, Any]] = None) -> Optional[RouterDecision]:
        if self._model_registry is None:
            return None
        candidates = self._model_registry.find_candidates(required_capabilities)
        if not candidates:
            return None
        strategy = self._strategy
        if strategy == "local_first":
            candidates.sort(key=lambda m: (not m.local, m.cost))
        elif strategy == "cost":
            candidates.sort(key=lambda m: (m.cost, m.local, not m.local))
        else:
            candidates.sort(key=lambda m: (m.cost, m.local))
        best = candidates[0]
        logger.info("Capability-based selection for %s: %s (caps=%s, strategy=%s)", task_type.value if task_type else "any", best.id, required_capabilities, strategy)
        return RouterDecision(
            provider_id=best.provider, model=best.id, task_type=task_type or TaskType.QUICK,
            strategy=f"capability_{strategy}", reason=f"Capability: {best.id} matched {required_capabilities}",
            selection_trace={"candidates": [m.id for m in candidates], "required_capabilities": required_capabilities},
        )

    def _try_select_from_registry(self, task_type: TaskType, context: Optional[Dict[str, Any]] = None) -> Optional[RouterDecision]:
        if self._model_registry is None:
            return None
        required_caps = self._task_capability_map.get(task_type, [])
        if not required_caps:
            return None
        candidates = self._model_registry.find_candidates(required_caps)
        if not candidates:
            return None
        strategy = self._strategy
        if strategy == "local_first":
            candidates.sort(key=lambda m: (not m.local, m.cost))
        elif strategy == "cost":
            candidates.sort(key=lambda m: (m.cost, m.local, not m.local))
        else:
            candidates.sort(key=lambda m: (m.cost, m.local))
        best = candidates[0]
        logger.info("Registry-based selection for %s: %s (caps=%s, strategy=%s)", task_type.value, best.id, required_caps, strategy)
        return RouterDecision(
            provider_id=best.provider, model=best.id, task_type=task_type,
            strategy=f"registry_{strategy}", reason=f"Registry: {best.id} matched capabilities {required_caps}",
            selection_trace={"candidates": [m.id for m in candidates], "required_capabilities": required_caps},
        )
