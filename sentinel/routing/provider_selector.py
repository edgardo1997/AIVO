import logging
import time
from typing import Any, Callable, Dict, List, Optional
from sentinel.core.router_types import TaskType, ProviderSpec, RouterDecision, ProviderAvailability, ROUTING_STRATEGIES, OFFLINE_MODES
from sentinel.core.hardware_intelligence import HardwareProfile, ModelCapabilityManager, get_model_capabilities
from sentinel.core.model_registry import ModelRegistry, TASK_CAPABILITY_MAP
from sentinel.core.model_tier import (
    ExecutionMode,
    ModelTier,
    ModelTierDecision,
    ModelTierSelector,
    tier_for_provider,
)
from sentinel.core.provider_performance import ProviderPerformanceStore
from sentinel.core.circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)

# ── Resource-aware soft-scoring configuration ────────────────────────────────
# Every component is normalized to 0.0–1.0. Missing data yields the documented
# neutral value below; it is never treated as "unlimited resources".
#   component        source                                   missing-data value
#   resource_fit     ResourceIntelligenceLayer (local only)   0.5 (neutral)
#   provider_health  availability cache / health checker      0.5 (neutral)
#   cost_fit         CostTracker price per 1k tokens          0.5 (neutral)
#   power_fit        SystemSnapshot battery/power-saver       1.0 (no penalty)
#   privacy_fit      request context permission level         1.0 (no penalty)
RESOURCE_WEIGHTS = {
    "resource_fit": 0.35,
    "provider_health": 0.25,
    "cost_fit": 0.15,
    "power_fit": 0.15,
    "privacy_fit": 0.10,
}
_NEUTRAL_SCORE = 0.5


class _CandidateModel:
    """Duck-typed model wrapper for ResourceIntelligenceLayer.evaluate()."""

    def __init__(self, model_id: str, provider_id: str, is_local: bool):
        self.id = model_id
        self.provider = provider_id
        self.local = is_local
        self.cost = 0.0
        self.speed = "unknown"


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
        self._resource_intelligence: Any = None
        self._tier_selector: Optional[ModelTierSelector] = None
        self._performance_store: Optional[ProviderPerformanceStore] = None

    def set_tier_selector(self, selector: ModelTierSelector) -> None:
        """Wire the tier selector (dependency injection)."""
        self._tier_selector = selector

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

    def set_resource_intelligence(self, layer: Any) -> None:
        """Wire the shared ResourceIntelligenceLayer (dependency injection, no singleton)."""
        self._resource_intelligence = layer

    def set_performance_store(self, store: ProviderPerformanceStore) -> None:
        """Wire the shared provider performance store."""
        self._performance_store = store

    def _provider_tier(self, provider: ProviderSpec) -> ModelTier:
        """Estimate the capability tier a provider can satisfy."""
        if self._model_registry is not None and provider.default_model:
            try:
                model = self._model_registry.get(provider.default_model)
                if model is not None:
                    from sentinel.core.model_tier import tier_for_model
                    return tier_for_model(model)
            except Exception:
                pass
        return tier_for_provider(provider)

    @staticmethod
    def _minimum_required_tier(tier_decision: Any) -> Optional[ModelTier]:
        if tier_decision is None:
            return None
        if isinstance(tier_decision, ModelTierDecision):
            return tier_decision.minimum_required_tier
        if isinstance(tier_decision, dict):
            val = tier_decision.get("minimum_required_tier")
            if val is not None:
                return ModelTier(val)
        return None

    @staticmethod
    def _execution_mode(tier_decision: Any) -> Optional[str]:
        if tier_decision is None:
            return None
        if isinstance(tier_decision, ModelTierDecision):
            return tier_decision.execution_mode.value
        if isinstance(tier_decision, dict):
            return tier_decision.get("execution_mode")
        return None

    # ── Resource stage: one snapshot per select(), hard gates + soft scoring ──

    def _capture_snapshot(self) -> Optional[Any]:
        """At most one SystemSnapshot per select() call. Failure → None + reason recorded."""
        if getattr(self, "_resource_intelligence", None) is None:
            return None
        try:
            return self._resource_intelligence.snapshot()
        except Exception as e:
            logger.warning("SystemSnapshot capture failed; using conservative defaults: %s", e)
            return None

    @staticmethod
    def _snapshot_summary(snap: Optional[Any]) -> Dict[str, Any]:
        """Non-sensitive operational summary only (no device names, paths or key data)."""
        if snap is None:
            return {"snapshot_unavailable": True}
        cpu = getattr(snap, "cpu_load_pct", 0.0)
        band = "low" if cpu < 50 else ("medium" if cpu <= 80 else "high")
        return {
            "ram_pressure_pct": round(100.0 - snap.ram_available_pct, 1),
            "cpu_load_band": band,
            "on_battery": snap.on_battery,
            "power_saver_active": snap.power_saver_active,
            "online": snap.online,
        }

    def _resource_hard_gate(
        self, provider: ProviderSpec, model: str, snap: Optional[Any], context: Optional[Dict[str, Any]]
    ) -> Optional[str]:
        """Deterministic hard gate. Returns a reason code or None (allowed).

        Local candidates: physical resource requirements apply (RAM/VRAM).
        Cloud candidates: local RAM/VRAM never apply; privacy and budget do.
        """
        ctx = context or {}
        if not provider.is_local:
            if ctx.get("cloud_allowed") is False:
                return "privacy_forbids_cloud"
            if snap is not None and snap.has_budget_constraint and self._cost_tracker is not None:
                try:
                    price = self._cost_tracker.get_model_price(provider.id, model)
                    if price > 0 and price > snap.budget_remaining_usd:
                        return "budget_exceeded"
                except Exception:
                    logger.debug("Budget gate skipped for %s: cost lookup failed", provider.id)
            return None
        # Local candidate: physical-resource gate via ResourceIntelligenceLayer
        layer = getattr(self, "_resource_intelligence", None)
        if layer is None or snap is None:
            return None  # gate unavailable; static capability gate (_hardware_allows) still applies
        try:
            decision = layer.evaluate(_CandidateModel(model, provider.id, True), snap)
            if not decision.allowed:
                return decision.restrictions[0] if decision.restrictions else "resource_rejected"
        except Exception:
            logger.debug("Resource gate skipped for %s: evaluate failed", provider.id)
        return None

    def _resource_components(
        self, provider: ProviderSpec, snap: Optional[Any], context: Optional[Dict[str, Any]]
    ) -> Dict[str, float]:
        """Normalized soft-scoring components (0.0–1.0 each) + weighted total."""
        ctx = context or {}
        comps: Dict[str, float] = {}
        layer = getattr(self, "_resource_intelligence", None)
        # resource_fit
        if provider.is_local and layer is not None and snap is not None:
            try:
                d = layer.evaluate(_CandidateModel(provider.default_model, provider.id, True), snap)
                comps["resource_fit"] = max(0.0, min(1.0, 0.5 + d.score_modifier / 100.0))
            except Exception:
                comps["resource_fit"] = _NEUTRAL_SCORE
        elif provider.is_local:
            comps["resource_fit"] = _NEUTRAL_SCORE
        else:
            comps["resource_fit"] = 1.0 if snap is not None else _NEUTRAL_SCORE
        # provider_health (availability cache is cheap and already TTL-cached)
        availability = self._availability_cache.get(provider.id)
        if availability is None:
            comps["provider_health"] = _NEUTRAL_SCORE
        else:
            comps["provider_health"] = 1.0 if availability.available else 0.0
        # cost_fit
        if not provider.requires_key:
            comps["cost_fit"] = 1.0
        elif self._cost_tracker is not None:
            try:
                price = self._cost_tracker.get_model_price(provider.id, provider.default_model)
                comps["cost_fit"] = 1.0 / (1.0 + price * 1000.0)
            except Exception:
                comps["cost_fit"] = _NEUTRAL_SCORE
        else:
            comps["cost_fit"] = _NEUTRAL_SCORE
        # power_fit: on battery/power-saver, heavier local execution is downgraded
        if snap is not None and (snap.power_saver_active or snap.on_battery):
            comps["power_fit"] = 0.6 if provider.is_local else 1.0
        else:
            comps["power_fit"] = 1.0
        # privacy_fit: privacy-sensitive contexts prefer local
        if ctx.get("permission_level") in ("high", "emergency") or ctx.get("privacy_prefers_local") is True:
            comps["privacy_fit"] = 1.0 if provider.is_local else 0.6
        else:
            comps["privacy_fit"] = 1.0

        # performance_fit: optional bounded, privacy-safe recent performance signal
        if self._performance_store is not None:
            try:
                comps["performance_fit"] = self._performance_store.performance_score(
                    provider.id, provider.default_model
                )
            except Exception:
                logger.debug("Performance score lookup failed for %s", provider.id)
                comps["performance_fit"] = _NEUTRAL_SCORE

        base_score = round(sum(RESOURCE_WEIGHTS[k] * comps[k] for k in RESOURCE_WEIGHTS), 4)
        # Performance is a soft, lower-precedence modifier.  It does not override
        # any of the hard or primary soft gates above.
        if "performance_fit" in comps:
            base_score += 0.1 * comps["performance_fit"]
        comps["score"] = round(base_score, 4)
        return comps

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

    def select(self, task_type: TaskType, context: Optional[Dict[str, Any]] = None, explicit_provider: Optional[str] = None, explicit_model: Optional[str] = None) -> RouterDecision:
        """
        Select provider with authoritative precedence:
        1. Explicit provider/model selected by user for current request
        2. Explicit provider/model configured as active preference
        3. Task capability requirements
        4. Security and privacy policy restrictions
        5. Provider health and actual availability
        6. Cost and latency strategy
        7. Default numeric priority (among same selection level)
        8. Local fallback when preferred external provider cannot be used
        """
        context = context or {}
        snapshot = self._capture_snapshot()  # at most one SystemSnapshot per select()
        snapshot_summary = self._snapshot_summary(snapshot)

        tier_decision = context.get("tier_decision")
        if self._execution_mode(tier_decision) == ExecutionMode.DETERMINISTIC.value:
            # Tier 0: no LLM call; execution layer governs deterministic actions
            return RouterDecision(
                provider_id="deterministic",
                model="deterministic",
                task_type=task_type,
                strategy="deterministic",
                reason="Tier 0 deterministic execution path",
                selection_trace={
                    "execution_mode": ExecutionMode.DETERMINISTIC.value,
                    "tier_decision": tier_decision.to_dict() if isinstance(tier_decision, ModelTierDecision) else tier_decision,
                    "snapshot_summary": snapshot_summary,
                },
            )

        # Level 1: Explicit user selection for this request
        if explicit_provider:
            provider = self._providers.get(explicit_provider)
            if not provider:
                raise ValueError(f"Explicit provider '{explicit_provider}' not found")
            if task_type not in provider.task_types:
                raise ValueError(f"Provider '{explicit_provider}' does not support task type '{task_type.value}'")

            requested_model = explicit_model or provider.default_model
            availability = self.provider_availability(explicit_provider)
            blocked_reason: Optional[str] = None
            if not availability.available:
                blocked_reason = availability.reason
            else:
                # Explicit selection does not bypass hard constraints
                gate = self._resource_hard_gate(provider, requested_model, snapshot, context)
                if gate is None and provider.is_local and not self._hardware_allows(provider, context):
                    gate = "hardware_incompatible"
                # Explicit selection must satisfy the minimum model tier if one is supplied
                min_tier = self._minimum_required_tier(tier_decision)
                if gate is None and min_tier is not None and self._provider_tier(provider) < min_tier:
                    gate = "tier_below_minimum"
                blocked_reason = gate
            if blocked_reason:
                # Never silently override; fallback manager applies the configured policy
                logger.warning(f"Explicit provider '{explicit_provider}' blocked: {blocked_reason}")
                return RouterDecision(
                    provider_id=explicit_provider,
                    model=requested_model,
                    task_type=task_type,
                    strategy="explicit",
                    reason=f"Explicit selection '{explicit_provider}' unavailable: {blocked_reason}",
                    selection_trace={
                        "requested_provider": explicit_provider,
                        "requested_model": requested_model,
                        "availability": availability.to_dict(),
                        "fallback_required": True,
                        "fallback_reason": blocked_reason,
                        "snapshot_summary": snapshot_summary,
                        "degraded_capability": {
                            "capability": task_type.value,
                            "status": "degraded",
                            "reason_code": blocked_reason,
                            "explanation": f"Requested {explicit_provider}/{requested_model} cannot run: {blocked_reason}",
                            "fallback": provider.fallback_chain or None,
                            "user_action_possible": blocked_reason in ("missing_api_key", "privacy_forbids_cloud", "budget_exceeded"),
                        },
                    },
                )

            # Explicit provider is available and passes hard constraints - use it
            logger.info(f"Explicit selection: {explicit_provider}/{requested_model}")
            return RouterDecision(
                provider_id=explicit_provider,
                model=requested_model,
                task_type=task_type,
                strategy="explicit",
                reason=f"Explicit user selection",
                selection_trace={
                    "requested_provider": explicit_provider,
                    "requested_model": explicit_model,
                    "actual_provider": explicit_provider,
                    "actual_model": requested_model,
                    "availability": availability.to_dict(),
                    "snapshot_summary": snapshot_summary,
                }
            )
        
        # Level 2: Configured preferred provider
        preferred_rejection: Optional[str] = None
        if self._preferred_provider:
            preferred = self._providers.get(self._preferred_provider)
            if preferred and task_type in preferred.task_types:
                availability = self.provider_availability(self._preferred_provider)
                gate = self._resource_hard_gate(preferred, preferred.default_model, snapshot, context)
                if availability.available and gate is None and self._hardware_allows(preferred, context):
                    logger.info(f"Using configured preferred provider: {self._preferred_provider}")
                    return RouterDecision(
                        provider_id=self._preferred_provider,
                        model=preferred.default_model,
                        task_type=task_type,
                        strategy="preferred",
                        reason=f"Configured preferred provider",
                        selection_trace={
                            "preferred_provider": self._preferred_provider,
                            "actual_provider": self._preferred_provider,
                            "actual_model": preferred.default_model,
                            "availability": availability.to_dict(),
                            "snapshot_summary": snapshot_summary,
                        }
                    )
                else:
                    preferred_rejection = gate or availability.reason
                    logger.warning(f"Preferred provider '{self._preferred_provider}' unavailable: {preferred_rejection}")
        
        # Level 3-7: Normal routing with smart or priority strategy
        if self._strategy == "smart":
            return self._smart_select(task_type, context)

        resource_rejections: Dict[str, str] = {}
        candidates = self._filter_candidates(task_type, context, snapshot=snapshot, rejections=resource_rejections)
        if not candidates:
            registry_decision = self._try_select_from_registry(task_type, context)
            if registry_decision is not None:
                return registry_decision
            exclusions = {
                p.id: resource_rejections.get(p.id) or self._candidate_exclusion_reason(p, context)
                for p in self._providers.values()
                if task_type in p.task_types
            }
            raise RuntimeError(f"No available provider supports task type '{task_type.value}'. Exclusions: {exclusions}")

        # Level 6: normalized resource soft-scoring among valid candidates
        # Level 7: numeric priority breaks ties within the same resource level
        components = {p.id: self._resource_components(p, snapshot, context) for p in candidates}
        if self._strategy == "local_first":
            candidates.sort(key=lambda p: (not p.is_local, -components[p.id]["score"], -p.priority))
        elif self._strategy == "cost":
            candidates.sort(key=lambda p: (p.requires_key, -components[p.id]["score"], -p.priority))
        else:
            candidates.sort(key=lambda p: (-components[p.id]["score"], -p.priority))

        best = candidates[0]
        excluded = {p.id: self._candidate_exclusion_reason(p, context) for p in self._providers.values() if task_type in p.task_types and p.id not in {c.id for c in candidates}}
        excluded.update(resource_rejections)
        hardware = self._hardware_trace(candidates, context)
        reason = f"Selected {best.id} for {task_type.value} (strategy={self._strategy}, resource_score={components[best.id]['score']}, priority={best.priority}, availability=verified)"
        if self._offline_reason:
            reason += f", offline={self._offline_reason}"
        logger.info(reason)
        return RouterDecision(
            provider_id=best.id, model=best.default_model, task_type=task_type,
            strategy=self._strategy, reason=reason,
            selection_trace={
                "eligible": [p.id for p in candidates], "excluded": excluded, "hardware": hardware,
                "offline_reason": self._offline_reason,
                "requested_provider": None, "requested_model": None,
                "actual_provider": best.id, "actual_model": best.default_model,
                "resource_rejections": resource_rejections,
                "resource_score_components": components,
                "snapshot_summary": snapshot_summary,
                "preferred_rejection": preferred_rejection,
                "tier_decision": tier_decision.to_dict() if isinstance(tier_decision, ModelTierDecision) else tier_decision,
            },
        )

    _SNAPSHOT_UNSET = object()

    def _filter_candidates(
        self,
        task_type: TaskType,
        context: Optional[Dict[str, Any]] = None,
        snapshot: Any = _SNAPSHOT_UNSET,
        rejections: Optional[Dict[str, str]] = None,
    ) -> List[ProviderSpec]:
        if snapshot is self._SNAPSHOT_UNSET:
            snapshot = self._capture_snapshot()
        offline = self.is_offline()
        result: List[ProviderSpec] = []
        for p in self._providers.values():
            if task_type not in p.task_types:
                continue
            if not self.provider_availability(p.id).available:
                continue
            if not self._hardware_allows(p, context):
                continue
            if offline and not p.is_local:
                continue
            gate = self._resource_hard_gate(p, p.default_model, snapshot, context)
            if gate is not None:
                if rejections is not None:
                    rejections[p.id] = gate
                continue
            min_tier = self._minimum_required_tier(context.get("tier_decision") if context else None)
            if min_tier is not None and self._provider_tier(p) < min_tier:
                if rejections is not None:
                    rejections[p.id] = "tier_below_minimum"
                continue
            result.append(p)
        return result

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
