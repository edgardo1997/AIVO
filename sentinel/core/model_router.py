from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterator, List, Optional
import logging
import os
import time
import uuid

from sentinel.core.router_types import (
    TaskType, ProviderSpec, RouterDecision, ProviderAvailability,
    BUILTIN_PROVIDERS, ROUTING_STRATEGIES, OFFLINE_MODES, PROVIDER_URLS,
    FALLBACK_STRATEGIES, TOTAL_TIMEOUT_BUDGET, CALL_TIMEOUT, LOCAL_CALL_TIMEOUT,
    CONNECT_TIMEOUT, FIRST_TOKEN_TIMEOUT_NONLOCAL, FIRST_TOKEN_TIMEOUT_LOCAL,
    STREAM_IDLE_TIMEOUT, classify_provider_error, format_elapsed,
)
from sentinel.routing.provider_selector import ProviderSelector
from sentinel.routing.capability_selector import CapabilitySelector
from sentinel.routing.fallback_manager import FallbackManager
from sentinel.providers.provider_manager import ProviderManager
from sentinel.execution.tool_executor import ToolExecutor
from sentinel.conversation.handler import ConversationHandler
from sentinel.monitoring.health_checker import HealthChecker
from sentinel.core.tool_schema_adapter import to_openai_tools, parse_tool_call, build_assistant_tool_message, build_tool_result_message, build_tool_error_message
from sentinel.intelligence.multi_model_coordinator import MultiModelCoordinator, MultiModelConfig
from sentinel.intelligence.evaluation_engine import ModelResponse

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_DEFAULT = "You are an AI assistant integrated into AIVO, a desktop productivity tool. Your purpose is to help the user with system monitoring, file management, task execution, and general computer assistance. Be concise, accurate, and helpful."


class ModelRouter:
    def __init__(
        self,
        providers: Optional[List[ProviderSpec]] = None,
        default_fallback_chain: Optional[List[str]] = None,
        fallback_strategy: str = "chain",
        max_fallbacks: int = 5,
        availability_checker: Optional[Callable[[ProviderSpec], ProviderAvailability]] = None,
        availability_ttl_seconds: float = 15.0,
        capability_manager: Optional[Any] = None,
        cloud_authority: Optional[Any] = None,
    ):
        resolved = {p.id: p for p in (BUILTIN_PROVIDERS if providers is None else providers)}
        self._providers: Dict[str, ProviderSpec] = resolved
        self._key_map: Dict[str, str] = {}
        self._strategy: str = "priority"
        self._preferred_provider: Optional[str] = None
        self._db = None
        self._feedback_store = None
        self._cost_tracker = None
        self._task_type_map: Dict[TaskType, str] = {}
        self._model_registry = None
        self._tool_gateway: Any = None
        self._tool_guard: Any = None
        self._health_checker = None
        self._offline_mode: str = "auto"
        self._offline_reason: Optional[str] = None
        self._routing_history: List[Dict[str, Any]] = []
        self._cloud_authority = cloud_authority
        import os
        self._canonical_chat = os.environ.get("SENTINEL_CANONICAL_CHAT", "1") != "0"

        from sentinel.core.hardware_intelligence import ModelCapabilityManager, get_model_capabilities
        from sentinel.core.model_registry import ModelRegistry, TASK_CAPABILITY_MAP
        from sentinel.core.circuit_breaker import CircuitBreaker
        from sentinel.core.budget import BudgetManager

        self._budget_manager = BudgetManager()
        from sentinel.core.metrics import MetricsStore
        self._metrics_store = MetricsStore()
        self._capability_manager = capability_manager or get_model_capabilities()
        self._task_capability_map: Dict[TaskType, List[str]] = {
            TaskType.CODE: TASK_CAPABILITY_MAP.get("coding", []),
            TaskType.REASONING: TASK_CAPABILITY_MAP.get("reasoning", []),
            TaskType.ANALYSIS: TASK_CAPABILITY_MAP.get("analysis", []),
            TaskType.QUICK: [], TaskType.CREATIVE: [],
            TaskType.LOCAL: TASK_CAPABILITY_MAP.get("local", []),
        }
        self._cb_store: CircuitBreaker = CircuitBreaker()
        self._default_fallback_chain: List[str] = default_fallback_chain or []
        self._fallback_strategy: str = fallback_strategy if fallback_strategy in FALLBACK_STRATEGIES else "chain"
        self._max_fallbacks: int = max(1, max_fallbacks)
        self._fallback_stats: Dict[str, int] = {}
        self._fallback_history: List[Dict[str, Any]] = []
        self._availability_checker = availability_checker
        self._availability_ttl_seconds = max(0.0, availability_ttl_seconds)
        self._availability_cache: Dict[str, ProviderAvailability] = {}
        self._tool_calling_max_recursion: int = 5

        self._provider_selector = ProviderSelector(
            providers=resolved,
            strategy=self._strategy,
            preferred_provider=self._preferred_provider,
            capability_manager=self._capability_manager,
            availability_checker=availability_checker,
            availability_ttl_seconds=availability_ttl_seconds,
        )
        self._provider_selector.set_task_capability_map(self._task_capability_map)
        self._capability_selector = CapabilitySelector()
        self._fallback_manager = FallbackManager(
            providers=resolved,
            default_fallback_chain=default_fallback_chain,
            fallback_strategy=fallback_strategy,
            max_fallbacks=max_fallbacks,
            circuit_breaker=self._cb_store,
            fallback_stats=self._fallback_stats,
            fallback_history=self._fallback_history,
        )
        self._provider_manager = ProviderManager(cloud_authority=self._cloud_authority)
        from sentinel.core.fallback_validator import FallbackValidator
        self._fallback_validator = FallbackValidator(self._provider_manager, self._budget_manager, self._cb_store)
        self._tool_executor = ToolExecutor(capability_selector=self._capability_selector)
        self._conversation_handler = ConversationHandler(chat_fn=self.chat)
        self._health_checker_component = HealthChecker()
        self._multi_model: Optional[MultiModelCoordinator] = None

        for pid, p in resolved.items():
            for pid2 in self._key_map:
                self._provider_selector.set_api_key(pid2, self._key_map[pid2])
                self._provider_manager.set_api_key(pid2, self._key_map[pid2])

    # ── Delegated public API ──────────────────────────────────────

    def set_feedback_store(self, store: Any) -> None:
        self._feedback_store = store
        self._provider_selector.set_feedback_store(store)

    def set_cost_tracker(self, tracker: Any) -> None:
        self._cost_tracker = tracker
        self._provider_selector.set_cost_tracker(tracker)

    def set_resource_intelligence(self, layer: Any) -> None:
        self._provider_selector.set_resource_intelligence(layer)

    def set_model_ranking(self, ranking: Any) -> None:
        self._provider_selector.set_ranking_engine(ranking)

    def set_database(self, db: Any) -> None:
        self._db = db

    def load_keys_from_db(self) -> None:
        if self._db is None:
            return
        try:
            rows = self._db.execute("SELECT provider_id, api_key FROM api_keys")
            for row in rows:
                self._key_map[row["provider_id"]] = row["api_key"]
                self._provider_selector.set_api_key(row["provider_id"], row["api_key"])
                self._provider_manager.set_api_key(row["provider_id"], row["api_key"])
        except Exception:
            logger.warning("Failed to load model provider keys from storage", exc_info=True)

    def save_keys_to_db(self) -> None:
        if self._db is None:
            return
        for pid, key in self._key_map.items():
            try:
                self._db.execute("INSERT OR REPLACE INTO api_keys (provider_id, api_key) VALUES (?, ?)", (pid, key))
            except Exception:
                logger.warning("Failed to persist model provider key for '%s'", pid, exc_info=True)

    def set_api_key(self, provider_id: str, key: str) -> None:
        self._key_map[provider_id] = key
        self._provider_selector.set_api_key(provider_id, key)
        self._provider_manager.set_api_key(provider_id, key)

    def delete_api_key(self, provider_id: str) -> bool:
        self._provider_selector.delete_api_key(provider_id)
        self._provider_manager.delete_api_key(provider_id)
        return bool(self._key_map.pop(provider_id, None))

    def close(self):
        """Close lifecycle-managed provider clients."""
        if self._provider_manager is not None:
            self._provider_manager.close()

    def has_api_key(self, provider_id: str) -> bool:
        return provider_id in self._key_map and bool(self._key_map[provider_id])

    def provider_availability(self, provider_id: str, refresh: bool = False) -> ProviderAvailability:
        return self._provider_selector.provider_availability(provider_id, refresh=refresh)

    def availability_snapshot(self, refresh: bool = False) -> Dict[str, Dict[str, Any]]:
        return self._provider_selector.availability_snapshot(refresh=refresh)

    def routing_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        return list(self._routing_history[-max(1, limit):])

    def _record_decision(self, decision: RouterDecision) -> RouterDecision:
        self._routing_history.append({"timestamp": time.time(), **decision.to_dict()})
        if len(self._routing_history) > 500:
            del self._routing_history[:-500]
        return decision

    def set_strategy(self, strategy: str) -> None:
        if strategy not in ROUTING_STRATEGIES:
            raise ValueError(f"Strategy must be one of {ROUTING_STRATEGIES}")
        self._strategy = strategy
        self._provider_selector.set_strategy(strategy)

    def set_preferred_provider(self, provider_id: Optional[str]) -> None:
        if provider_id and provider_id not in self._providers:
            raise KeyError(f"Provider '{provider_id}' not found")
        self._preferred_provider = provider_id or None
        self._provider_selector.set_preferred_provider(provider_id)

    def set_offline_mode(self, mode: str) -> None:
        if mode not in OFFLINE_MODES:
            raise ValueError(f"offline_mode must be one of {OFFLINE_MODES}")
        self._offline_mode = mode
        self._offline_reason = "offline_mode_forced" if mode == "force_local" else None
        self._provider_selector.set_offline_mode(mode)

    def get_offline_mode(self) -> str:
        return self._offline_mode

    def _is_cloud_authorized(self, provider_id: str, model_id: str, purpose: str = "conversation") -> bool:
        if not self._cloud_authority:
            return False
        return self._cloud_authority.is_authorized(provider_id, model_id, purpose)

    def _is_provider_ready(self, provider_id: str) -> bool:
        provider = self._providers.get(provider_id)
        if not provider or provider.is_local:
            from sentinel.local_model.runtime import get_local_runtime
            status = get_local_runtime().status()
            return status.get("state") in ("ready", "running")
        return True

    def set_cloud_authority(self, cloud_authority) -> None:
        self._cloud_authority = cloud_authority
        self._provider_manager.set_cloud_authority(cloud_authority)

    def set_health_checker(self, checker) -> None:
        self._health_checker = checker
        self._provider_selector.set_health_checker(checker)

    def is_offline(self) -> bool:
        return self._provider_selector.is_offline()

    def set_default_fallback_chain(self, chain: List[str]) -> None:
        self._default_fallback_chain = chain
        self._fallback_manager.set_default_fallback_chain(chain)

    def set_fallback_strategy(self, strategy: str) -> None:
        if strategy not in FALLBACK_STRATEGIES:
            raise ValueError(f"Fallback strategy must be one of {FALLBACK_STRATEGIES}")
        self._fallback_strategy = strategy
        self._fallback_manager.set_fallback_strategy(strategy)

    def set_max_fallbacks(self, n: int) -> None:
        self._max_fallbacks = max(1, n)
        self._fallback_manager.set_max_fallbacks(max(1, n))

    def set_task_type_map(self, mapping: Dict[TaskType, str]) -> None:
        self._task_type_map = mapping

    def set_task_type_map_from_dict(self, mapping: Dict[str, str]) -> None:
        self._task_type_map = {TaskType(k): v for k, v in mapping.items()}

    def set_model_registry(self, registry) -> None:
        self._model_registry = registry
        self._provider_selector.set_model_registry(registry)
        self._capability_selector.set_model_registry(registry)
        if self._multi_model is not None:
            try:
                self._multi_model.model_registry = registry
            except Exception:
                logger.warning("Failed to synchronize registry with multi-model coordinator", exc_info=True)

    def set_intelligence(self, intel) -> None:
        """Conecta el router al IntelligenceCoordinator (failover real)."""
        self._intelligence = intel
        try:
            intel.set_model_router(self)
        except Exception:
            logger.warning("Failed to connect intelligence coordinator to model router", exc_info=True)
        try:
            self._fallback_manager.set_failure_reporter(
                lambda provider_id, model, classification: self._notify_failure(provider_id, model)
            )
        except Exception:
            logger.warning("Failed to configure model fallback failure reporting", exc_info=True)

    def _notify_success(self, provider_id: str, model_id: str, latency_ms: float = 0.0, task_type: str = "chat") -> None:
        intel = getattr(self, "_intelligence", None)
        if intel is None:
            return
        try:
            import asyncio
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                return
            loop.create_task(intel.record_execution_result(
                provider_id=provider_id,
                model_id=model_id,
                success=True,
                latency_ms=latency_ms,
                task_type=task_type,
            ))
        except Exception:
            logger.warning("Failed to notify intelligence coordinator of model success", exc_info=True)

    def _notify_failure(self, provider_id: str, model_id: str) -> None:
        intel = getattr(self, "_intelligence", None)
        if intel is None:
            return
        try:
            import asyncio
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                return
            loop.create_task(intel.apply_provider_failure(provider_id, model_id))
        except Exception:
            logger.warning("Failed to notify intelligence coordinator of model failure", exc_info=True)

    def set_tool_gateway(self, gateway: Any) -> None:
        self._tool_gateway = gateway
        self._tool_executor.set_tool_gateway(gateway)

    def set_tool_guard(self, guard: Any) -> None:
        self._tool_guard = guard
        self._tool_executor.set_tool_guard(guard)

    def set_execution_pipeline(self, pipeline: Any) -> None:
        self._tool_executor.set_execution_pipeline(pipeline)

    def set_task_capability_map(self, task_type: TaskType, capabilities: List[str]) -> None:
        self._task_capability_map[task_type] = capabilities
        self._provider_selector.set_task_capability_map(self._task_capability_map)

    def enable_multi_model(self, config: Optional[Dict[str, Any]] = None) -> None:
        mm_config = MultiModelConfig(**(config or {}))
        self._multi_model = MultiModelCoordinator(
            config=mm_config,
            model_router=self,
            model_registry=self._model_registry,
        )

    def is_multi_model_enabled(self) -> bool:
        return self._multi_model is not None

    def select_by_capability(self, required_capabilities: List[str], task_type: Optional[TaskType] = None, context: Optional[Dict[str, Any]] = None) -> Optional[RouterDecision]:
        result = self._provider_selector.select_by_capability(required_capabilities, task_type=task_type, context=context)
        if result:
            return self._record_decision(result)
        return None

    def _validate_tool_call_compatibility(self, model_id: str, provider_id: str) -> bool:
        return self._capability_selector.validate_tool_call_compatibility(model_id, provider_id)

    async def _execute_tool_call_safe(self, tool_call: Dict[str, Any], provider_id: str, model_id: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return await self._tool_executor.execute_tool_call(tool_call, provider_id, model_id, context=context)

    async def _handle_tool_calls(self, tool_calls: List[Dict[str, Any]], provider_id: str, model_id: str, context: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        return await self._tool_executor.handle_tool_calls(tool_calls, provider_id, model_id, context=context)

    async def chat_with_tools(self, messages: List[Dict[str, str]], tools: List[Any], task_type: TaskType = TaskType.QUICK, model_override: Optional[str] = None, context: Optional[Dict[str, Any]] = None, max_tool_rounds: int = 5) -> Dict[str, Any]:
        context = context or {}
        openai_tools = to_openai_tools(tools)
        if not openai_tools:
            logger.info("No active tools to send — falling back to normal chat")
            return self.chat(messages, task_type=task_type, model_override=model_override, context=context)
        tool_calling_caps = ["tool_calling"]
        if self._model_registry:
            candidates = self._model_registry.find_candidates(tool_calling_caps)
            if not candidates:
                logger.warning("No models with supports_tool_calling=True — falling back to normal chat")
                return self.chat(messages, task_type=task_type, model_override=model_override, context=context)
        decision = self.select(task_type, context=context)
        provider = self._providers.get(decision.provider_id)
        if not provider:
            return self.chat(messages, task_type=task_type, model_override=model_override, context=context)
        current_messages = list(messages)
        model_id = model_override or decision.model
        last_response = None
        total_elapsed = 0.0
        for round_idx in range(max_tool_rounds + 1):
            elapsed = time.monotonic()
            try:
                result = self._provider_manager.execute_inference(decision, provider, current_messages, model_override=model_override, tools=openai_tools)
            except Exception as e:
                raise RuntimeError(f"Provider call failed in chat_with_tools: {e}") from e
            elapsed = time.monotonic() - elapsed
            total_elapsed += elapsed
            tool_calls = result.get("tool_calls", [])
            if not tool_calls:
                last_response = result
                last_response["tool_calling_rounds"] = round_idx
                last_response["total_elapsed_seconds"] = total_elapsed
                return last_response
            try:
                tool_msgs = await self._handle_tool_calls(tool_calls, decision.provider_id, model_id, context=context)
            except RuntimeError as e:
                last_response = result
                last_response["tool_calling_rounds"] = round_idx
                last_response["total_elapsed_seconds"] = total_elapsed
                last_response["tool_calling_error"] = str(e)
                return last_response
            assistant_msg = build_assistant_tool_message(tool_calls)
            current_messages.append(assistant_msg)
            current_messages.extend(tool_msgs)
        logger.warning("Max tool calling rounds (%d) reached", max_tool_rounds)
        if last_response is None:
            return self.chat(messages, task_type=task_type, model_override=model_override, context=context)
        last_response["tool_calling_rounds"] = max_tool_rounds
        last_response["total_elapsed_seconds"] = total_elapsed
        last_response["tool_calling_truncated"] = True
        return last_response

    def fallback_stats(self) -> Dict[str, Any]:
        return self._fallback_manager.fallback_stats()

    def reset_fallback_stats(self) -> int:
        return self._fallback_manager.reset_fallback_stats()

    def _build_fallback_chain(self, primary: RouterDecision, task_type: TaskType, context: Optional[Dict[str, Any]] = None) -> List[RouterDecision]:
        return self._fallback_manager.build_fallback_chain(
            primary, task_type, context=context,
            provider_availability_fn=self.provider_availability,
            select_all_fn=self.select_all,
        )

    def _record_fallback(self, provider_id: str, category: str = "unknown") -> None:
        self._fallback_manager.record_fallback(provider_id, category=category)

    def _try_select_from_registry(self, task_type: TaskType, context: Optional[Dict[str, Any]] = None) -> Optional[RouterDecision]:
        return self._provider_selector._try_select_from_registry(task_type, context=context)

    def select(self, task_type: TaskType, context: Optional[Dict[str, Any]] = None, explicit_provider: Optional[str] = None, explicit_model: Optional[str] = None) -> RouterDecision:
        # If explicit provider/model is specified, bypass registry and go directly to provider selector
        if explicit_provider or explicit_model:
            return self._record_decision(self._provider_selector.select(task_type, context=context, explicit_provider=explicit_provider, explicit_model=explicit_model))
        registry_decision = self._try_select_from_registry(task_type, context)
        if registry_decision is not None:
            return self._record_decision(registry_decision)
        return self._record_decision(self._provider_selector.select(task_type, context=context))

    def _filter_candidates(self, task_type: TaskType, context: Optional[Dict[str, Any]] = None) -> List[ProviderSpec]:
        return self._provider_selector._filter_candidates(task_type, context=context)

    @staticmethod
    def _hardware_profile(context: Optional[Dict[str, Any]]) -> Optional[Any]:
        return ProviderSelector._hardware_profile(context)

    def _hardware_assessment(self, provider: ProviderSpec, context: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        return self._provider_selector._hardware_assessment(provider, context)

    def _hardware_allows(self, provider: ProviderSpec, context: Optional[Dict[str, Any]]) -> bool:
        return self._provider_selector._hardware_allows(provider, context)

    def _candidate_exclusion_reason(self, provider: ProviderSpec, context: Optional[Dict[str, Any]]) -> str:
        return self._provider_selector._candidate_exclusion_reason(provider, context)

    def _hardware_trace(self, candidates: List[ProviderSpec], context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        return self._provider_selector._hardware_trace(candidates, context)

    def _smart_select(self, task_type: TaskType, context: Dict[str, Any]) -> RouterDecision:
        return self._provider_selector._smart_select(task_type, context)

    def select_all(self, task_type: TaskType, context: Optional[Dict[str, Any]] = None) -> List[RouterDecision]:
        return self._provider_selector.select_all(task_type, context=context)

    def route(self, request: "ModelRequest") -> "RoutingDecision":
        """Canonical routing entry point: ModelRequest -> RoutingDecision."""
        import time
        route_start = time.monotonic()
        from sentinel.core.model_schemas import (
            CapabilityStatus,
            FallbackPolicy,
            ModelCandidate,
            ModelRequest,
            RoutingDecision,
            SelectionReasonCode,
        )
        from sentinel.core.router_types import TaskType

        task_type = TaskType(request.task_type) if request.task_type in {t.value for t in TaskType} else TaskType.QUICK
        existing_decision = self.select(
            task_type,
            explicit_provider=request.provider_preference,
            explicit_model=request.model_preference,
        )
        candidates: List[ModelCandidate] = []
        for p in self._providers.values():
            cand = ModelCandidate(
                provider_id=p.id,
                model_id=p.default_model,
                model_name=p.default_model,
                is_local=p.is_local,
                is_cloud=not p.is_local,
                capabilities=[
                    {"name": c, "status": CapabilityStatus.DECLARED}
                    for c in getattr(self._capability_manager, "capabilities_for", lambda m: [])(p.default_model)
                ],
                healthy=True,
            )
            if p.id != existing_decision.provider_id:
                cand.reason_excluded = "not_selected"
            candidates.append(cand)

        # ── Authority check before final selection ───────────────────
        selected_provider = existing_decision.provider_id
        selected_model = existing_decision.model
        reason = SelectionReasonCode.LOCAL_CAPABLE_PREFERRED
        is_cloud = not self._providers.get(selected_provider, ProviderSpec(id=selected_provider, name=selected_provider, task_types=[], is_local=False)).is_local
        if is_cloud and (not request.cloud_allowed or not self._is_cloud_authorized(selected_provider, selected_model, "conversation")):
            # Try a local fallback when cloud is not authorized
            local = next(
                (c for c in candidates if c.is_local and self._is_provider_ready(c.provider_id)),
                None,
            )
            if local:
                selected_provider = local.provider_id
                selected_model = local.model_id
                reason = SelectionReasonCode.LOCAL_SELECTED_CLOUD_NOT_AUTHORIZED
            else:
                from sentinel.core.model_errors import RoutingError
                raise RoutingError(
                    "SEN-MODEL-CLOUD-NOT-AUTHORIZED",
                    f"Cloud provider {selected_provider} is not authorized",
                    retryable=False,
                )

        # ── Budget reservation before final selection ────────────────
        estimate = self._estimate_cost(selected_provider, selected_model, request.context_tokens)
        budget_ok = self._budget_manager.reserve(selected_provider, selected_model, estimate)
        if not budget_ok:
            # Try local fallback if over budget
            local = next((c for c in candidates if c.is_local and c.healthy), None)
            if local and local.provider_id != selected_provider:
                alt_estimate = self._estimate_cost(local.provider_id, local.model_id, request.context_tokens)
                if self._budget_manager.reserve(local.provider_id, local.model_id, alt_estimate):
                    self._budget_manager.release(selected_provider, selected_model, estimate)
                    selected_provider = local.provider_id
                    selected_model = local.model_id
                    estimate = alt_estimate
                    reason = SelectionReasonCode.LOWEST_ESTIMATED_COST
                else:
                    reason = SelectionReasonCode.BUDGET_EXCEEDED
            else:
                reason = SelectionReasonCode.BUDGET_EXCEEDED

        if selected_provider != "sentinel_local" and not any(c.is_local for c in candidates if c.provider_id == selected_provider):
            if not request.cloud_allowed:
                reason = SelectionReasonCode.CLOUD_NOT_AUTHORIZED
        if request.provider_preference and selected_provider == request.provider_preference:
            reason = SelectionReasonCode.USER_PROVIDER_PREFERENCE_ALLOWED

        decision = RoutingDecision(
            selected_provider=selected_provider,
            selected_model=selected_model,
            selection_reason_code=reason,
            candidate_count=len(candidates),
            matched_capabilities=request.required_capabilities,
            missing_capabilities=[],
            cloud_used=not self._providers.get(selected_provider, ProviderSpec(id=selected_provider, name=selected_provider, task_types=[], is_local=False)).is_local,
            authority_reference=request.cloud_authority_reference,
            estimated_cost=estimate,
            estimated_latency_ms=0,
            fallback_chain=existing_decision.fallback_chain if hasattr(existing_decision, "fallback_chain") else [],
            confidence="high",
            candidates=candidates,
            safe_explanation=f"Selected {selected_model} from {selected_provider} using {reason.value}.",
        )

        from sentinel.core.metrics import RoutingMetric
        self._metrics_store.record(RoutingMetric(
            request_id=request.request_id,
            correlation_id=request.correlation_id,
            provider=selected_provider,
            model=selected_model,
            operation="route",
            routing_reason=reason.value,
            candidate_count=len(candidates),
            latency_ms=(time.monotonic() - route_start) * 1000,
            time_to_first_token_ms=None,
            input_tokens=request.context_tokens,
            output_tokens=0,
            total_tokens=request.context_tokens,
            estimated_cost=estimate,
            reserved_cost=estimate,
            actual_cost=0.0,
            fallback_used=False,
            fallback_reason="",
            status="completed",
            error_code="",
        ))

        return decision

    def execute(self, request: "ModelRequest", messages: List[Dict[str, str]]) -> Dict[str, Any]:
        """Canonical execution: route then execute through ProviderManager."""
        decision = self.route(request)
        provider = self._providers.get(decision.selected_provider)
        if provider is None:
            raise RuntimeError(f"Unknown provider selected: {decision.selected_provider}")
        rt_decision = RouterDecision(
            provider_id=provider.id,
            model=decision.selected_model,
            task_type=TaskType(request.task_type) if request.task_type in {t.value for t in TaskType} else TaskType.QUICK,
            strategy=self._strategy,
            reason=decision.selection_reason_code,
        )
        return self._provider_manager.execute_inference(rt_decision, provider, messages)

    def execute_stream(self, request: "ModelRequest", messages: List[Dict[str, str]]) -> Iterator[Dict[str, Any]]:
        """Canonical streaming execution that wraps provider events into StreamEvent."""
        from sentinel.core.model_schemas import StreamEvent, StreamEventType
        import time
        stream_started = time.time()
        decision = self.route(request)
        provider = self._providers.get(decision.selected_provider)
        if provider is None:
            raise RuntimeError(f"Unknown provider selected: {decision.selected_provider}")
        rt_decision = RouterDecision(
            provider_id=provider.id,
            model=decision.selected_model,
            task_type=TaskType(request.task_type) if request.task_type in {t.value for t in TaskType} else TaskType.QUICK,
            strategy=self._strategy,
            reason=decision.selection_reason_code,
        )
        seq = 0
        started = False
        has_emitted_delta = False
        first_token_at = None
        try:
            for raw in self._provider_manager.execute_inference_stream(rt_decision, provider, messages):
                if not started:
                    started = True
                    yield StreamEvent(
                        event_type=StreamEventType.STARTED,
                        request_id=request.request_id,
                        correlation_id=request.correlation_id,
                        provider=provider.id,
                        model=decision.selected_model,
                        sequence=seq,
                        timestamp=time.time(),
                        payload={"selection": {"provider": provider.id, "model": decision.selected_model}},
                    ).model_dump()
                    seq += 1
                if raw.get("type") == "delta" or raw.get("content") or raw.get("text"):
                    has_emitted_delta = True
                    if first_token_at is None:
                        first_token_at = time.time()
                    yield StreamEvent(
                        event_type=StreamEventType.DELTA,
                        request_id=request.request_id,
                        correlation_id=request.correlation_id,
                        provider=provider.id,
                        model=decision.selected_model,
                        sequence=seq,
                        timestamp=time.time(),
                        payload={"content": raw.get("text", raw.get("content", "")), "delta": raw},
                    ).model_dump()
                    seq += 1
                elif raw.get("type") == "usage" or raw.get("usage"):
                    yield StreamEvent(
                        event_type=StreamEventType.USAGE,
                        request_id=request.request_id,
                        correlation_id=request.correlation_id,
                        provider=provider.id,
                        model=decision.selected_model,
                        sequence=seq,
                        timestamp=time.time(),
                        payload={"usage": raw.get("usage", raw)},
                    ).model_dump()
                    seq += 1
        except Exception as exc:
            if has_emitted_delta:
                yield StreamEvent(
                    event_type=StreamEventType.FAILED,
                    request_id=request.request_id,
                    correlation_id=request.correlation_id,
                    provider=provider.id,
                    model=decision.selected_model,
                    sequence=seq,
                    timestamp=time.time(),
                    payload={"partial_output": True},
                    error_code="SEN-MODEL-STREAM-FAILED",
                    safe_message="Stream failed after content was emitted",
                ).model_dump()
            else:
                # Before first delta, let caller retry fallback
                raise
            return
        yield StreamEvent(
            event_type=StreamEventType.COMPLETED,
            request_id=request.request_id,
            correlation_id=request.correlation_id,
            provider=provider.id,
            model=decision.selected_model,
            sequence=seq,
            timestamp=time.time(),
            payload={"first_token_latency_ms": (first_token_at - stream_started) * 1000 if first_token_at else None},
        ).model_dump()

    def set_circuit_breaker(self, cb) -> None:
        self._cb_store = cb
        self._fallback_manager.set_circuit_breaker(cb)

    def _estimate_cost(self, provider_id: str, model: str, tokens: int) -> float:
        """Return a crude cost estimate per 1k tokens."""
        from sentinel.core.cost_tracker import MODEL_PRICING
        by_provider = MODEL_PRICING.get(provider_id, {})
        per_1k = by_provider.get(model, by_provider.get("default", 0.0))
        return (tokens / 1000.0) * per_1k

    def _filter_open_providers(self, candidates: List[RouterDecision]) -> List[RouterDecision]:
        return self._fallback_manager.filter_open_providers(candidates)

    def _chat_canonical(self, messages: List[Dict[str, str]], task_type: TaskType = TaskType.QUICK, model_override: Optional[str] = None, context: Optional[Dict[str, Any]] = None, fallback_chain_override: Optional[List[str]] = None) -> Dict[str, Any]:
        from sentinel.core.context_validator import ContextWindowValidator
        from sentinel.core.model_schemas import FallbackPolicy, ModelCapability, ModelCandidate, ModelRequest, CapabilityStatus
        context = context or {}
        capabilities = ["chat"]
        if task_type == TaskType.CODE:
            capabilities.append("coding")
        elif task_type == TaskType.REASONING:
            capabilities.append("reasoning")
        validator = ContextWindowValidator()
        system_prompt = context.get("system_prompt", "")
        context_tokens = validator.estimate_request_tokens(system_prompt, messages, tool_schemas=context.get("tools"))
        request = ModelRequest(
            task_type=task_type.value,
            required_capabilities=capabilities,
            context_tokens=context_tokens,
            fallback_policy=FallbackPolicy.ORDERED_CHAIN,
            cloud_allowed=not self._offline_mode == "forced" and not bool(context.get("local_only")),
            local_only=bool(context.get("local_only")),
            cloud_authority_reference=context.get("cloud_authority_reference", ""),
        )
        try:
            decision = self.route(request)
        except Exception as exc:
            if not self._providers:
                raise RuntimeError(str(exc)) from exc
            return self._to_safe_error("SEN-MODEL-ROUTING-FAILED", str(exc), request.correlation_id)
        primary = self._providers.get(decision.selected_provider)
        if not primary:
            if not self._providers:
                raise RuntimeError("No providers available")
            return self._to_safe_error("SEN-MODEL-ROUTING-FAILED", "Unknown provider selected", request.correlation_id)
        # Context revalidation is still a known gap pending model metadata for the selected candidate.
        try:
            result = self.execute(request, messages)
        except Exception as exc:
            candidates: List[ModelCandidate] = []
            ordered_ids = fallback_chain_override if fallback_chain_override else [pid for pid in self._providers if pid != decision.selected_provider]
            for pid in ordered_ids:
                spec = self._providers.get(pid)
                if not spec:
                    continue
                if request.local_only and not spec.is_local:
                    continue
                candidates.append(ModelCandidate(
                    provider_id=pid,
                    model_id=spec.default_model or model_override or "",
                    is_local=spec.is_local,
                    capabilities=[ModelCapability(name="chat", status=CapabilityStatus.DECLARED)],
                    healthy=True,
                ))
            for candidate in candidates[: self._max_fallbacks]:
                try:
                    self._fallback_validator.revalidate(request, candidate, messages, request.context_tokens)
                except Exception:
                    continue
                fb_request = request.model_copy(update={"provider_preference": candidate.provider_id})
                try:
                    result = self.execute(fb_request, messages)
                    self._record_fallback(candidate.provider_id, category="chat")
                    break
                except Exception:
                    continue
            else:
                return self._to_safe_error("SEN-PROVIDER-UNAVAILABLE", str(exc), request.correlation_id)
        rt_decision = RouterDecision(provider_id=decision.selected_provider, model=decision.selected_model, task_type=task_type, strategy="priority", reason=decision.selection_reason_code)
        return self._to_legacy_response(result, rt_decision, request)

    def _to_safe_error(self, code: str, message: str, correlation_id: str) -> Dict[str, Any]:
        from sentinel.core.model_errors import RoutingError
        return RoutingError(
            code=code,
            safe_message=message,
            retryable=code not in {"SEN-MODEL-CONTEXT-EXCEEDED", "SEN-MODEL-CLOUD-NOT-AUTHORIZED"},
            details={"correlation_id": correlation_id},
        ).to_safe_dict(correlation_id=correlation_id)

    def chat(self, messages: List[Dict[str, str]], task_type: TaskType = TaskType.QUICK, model_override: Optional[str] = None, context: Optional[Dict[str, Any]] = None, fallback_chain_override: Optional[List[str]] = None) -> Dict[str, Any]:
        if self._canonical_chat:
            return self._chat_canonical(messages, task_type=task_type, model_override=model_override, context=context, fallback_chain_override=fallback_chain_override)
        context = context or {}
        decision = self.select(task_type, context=context)
        try:
            result = self._fallback_manager.execute_with_fallback(
                decision, task_type, messages, self._providers,
                lambda c, p, msgs, mo, **kw: self._call_provider(c, p, msgs, mo, **kw),
                model_override=model_override, context=context,
                fallback_chain_override=fallback_chain_override,
                provider_availability_fn=self.provider_availability,
                select_all_fn=self.select_all,
            )
            if self._cost_tracker and result.get("usage"):
                usage = result["usage"]
                self._cost_tracker.record_cost(
                    provider_id=result["selection"]["used"],
                    model=result["selection"]["model"],
                    task_type=task_type,
                    prompt_tokens=usage.get("prompt_tokens", 0),
                    completion_tokens=usage.get("completion_tokens", 0),
                )
            self._notify_success(
                provider_id=result.get("selection", {}).get("used", decision.provider_id),
                model_id=result.get("selection", {}).get("model", decision.model),
                task_type=task_type.value if hasattr(task_type, "value") else str(task_type),
            )
            return result
        except RuntimeError:
            self._notify_failure(decision.provider_id, decision.model)
            raise

    async def chat_multi_model(self, user_message: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not self._multi_model:
            raise RuntimeError("Multi-model mode not enabled. Call enable_multi_model() first.")

        async def execute_fn(task: Dict[str, Any]) -> ModelResponse:
            provider = self._providers.get(task.get("provider", ""))
            if not provider:
                return ModelResponse(model_id=task.get("model_id", "unknown"), provider=task.get("provider", "unknown"), response_text="", success=False, error="Unknown provider")
            messages = [{"role": "user", "content": task.get("objective", user_message)}]
            try:
                result = self._provider_manager.execute_inference(
                    RouterDecision(
                        provider_id=task["provider"],
                        model=task["model_id"],
                        task_type=TaskType.ANALYSIS,
                        strategy="multi_model",
                        reason="Multi-model coordination",
                    ),
                    provider,
                    messages,
                )
                return ModelResponse(
                    model_id=task["model_id"],
                    provider=task["provider"],
                    response_text=result.get("response", ""),
                    success=True,
                )
            except Exception as e:
                return ModelResponse(
                    model_id=task["model_id"],
                    provider=task["provider"],
                    response_text="",
                    success=False,
                    error=str(e)[:200],
                )

        mm_result = await self._multi_model.process(user_message, execute_fn=execute_fn, context=context)
        return mm_result.to_dict()

    def _to_legacy_meta(self, first_event: Dict[str, Any], routing_decision, is_fallback: bool = False, actual_provider: Optional[str] = None, actual_model: Optional[str] = None) -> Dict[str, Any]:
        return {
            "type": "meta",
            "request_id": first_event.get("request_id", ""),
            "correlation_id": first_event.get("correlation_id", ""),
            "provider": actual_provider or first_event.get("provider", ""),
            "model": actual_model or first_event.get("model", ""),
            "requested_provider": routing_decision.selected_provider,
            "requested_model": routing_decision.selected_model,
            "actual_provider": actual_provider or first_event.get("provider", ""),
            "actual_model": actual_model or first_event.get("model", ""),
            "fallback_required": is_fallback,
            "route": "conversation",
        }

    def _chat_stream_canonical(self, messages: List[Dict[str, str]], task_type: TaskType = TaskType.QUICK, model_override: Optional[str] = None, context: Optional[Dict[str, Any]] = None, explicit_provider: Optional[str] = None, explicit_model: Optional[str] = None, fallback_chain_override: Optional[List[str]] = None) -> Iterator[Dict[str, Any]]:
        from sentinel.core.model_schemas import FallbackPolicy, ModelRequest
        context = context or {}
        capabilities = ["chat"]
        if task_type == TaskType.CODE:
            capabilities.append("coding")
        elif task_type == TaskType.REASONING:
            capabilities.append("reasoning")
        from sentinel.core.context_validator import ContextWindowValidator
        validator = ContextWindowValidator()
        system_prompt = context.get("system_prompt", "")
        context_tokens = validator.estimate_request_tokens(system_prompt, messages, tool_schemas=context.get("tools"))
        request = ModelRequest(
            task_type=task_type.value,
            required_capabilities=capabilities,
            context_tokens=context_tokens,
            fallback_policy=FallbackPolicy.ORDERED_CHAIN,
            cloud_allowed=not self._offline_mode == "forced" and not bool(context.get("local_only")),
            local_only=bool(context.get("local_only")),
            cloud_authority_reference=context.get("cloud_authority_reference", ""),
            provider_preference=explicit_provider,
            model_preference=explicit_model,
            correlation_id=context.get("correlation_id", ""),
        )
        routing_decision = self.route(request)
        primary_gen = self.execute_stream(request, messages)
        try:
            first = next(primary_gen)
            yield self._to_legacy_meta(first, routing_decision, is_fallback=False)
            yield first
            yield from primary_gen
            return
        except Exception:
            pass
        # Before first delta: fallback allowed. Build fallback candidates from remaining providers.
        primary_decision = self.route(request)
        if fallback_chain_override:
            ordered_ids = list(fallback_chain_override)
        else:
            remaining = [p for p in self._providers if p != primary_decision.selected_provider]
            ordered_ids = sorted(remaining, key=lambda pid: 0 if self._providers.get(pid, ProviderSpec(id=pid, name=pid, task_types=[], is_local=False)).is_local else 1)
        from sentinel.core.model_schemas import CapabilityStatus, ModelCandidate, ModelCapability
        for pid in ordered_ids[: self._max_fallbacks]:
            spec = self._providers.get(pid)
            if not spec:
                continue
            if request.local_only and not spec.is_local:
                continue
            candidate = ModelCandidate(
                provider_id=pid,
                model_id=spec.default_model or model_override or "",
                is_local=spec.is_local,
                capabilities=[ModelCapability(name="chat", status=CapabilityStatus.DECLARED)],
                healthy=True,
            )
            try:
                self._fallback_validator.revalidate(request, candidate, messages, request.context_tokens)
            except Exception:
                continue
            fb_request = request.model_copy(update={"provider_preference": candidate.provider_id})
            fb_gen = self.execute_stream(fb_request, messages)
            try:
                first = next(fb_gen)
                yield self._to_legacy_meta(first, routing_decision, is_fallback=True, actual_provider=candidate.provider_id, actual_model=candidate.model_id)
                yield first
                yield from fb_gen
                self._record_fallback(candidate.provider_id, "stream")
                return
            except Exception:
                continue
        from sentinel.core.model_schemas import StreamEvent, StreamEventType
        yield StreamEvent(
            event_type=StreamEventType.FAILED,
            request_id=request.request_id,
            correlation_id=request.correlation_id,
            provider=primary_decision.selected_provider,
            model=primary_decision.selected_model,
            sequence=0,
            timestamp=time.time(),
            payload={"partial_output": False},
            error_code="SEN-MODEL-STREAM-FAILED",
            safe_message="All providers failed for streaming",
        ).model_dump()

    def chat_stream(self, messages: List[Dict[str, str]], task_type: TaskType = TaskType.QUICK, model_override: Optional[str] = None, context: Optional[Dict[str, Any]] = None, explicit_provider: Optional[str] = None, explicit_model: Optional[str] = None, fallback_chain_override: Optional[List[str]] = None) -> Iterator[Dict[str, Any]]:
        yield from self._chat_stream_canonical(messages, task_type=task_type, model_override=model_override, context=context, explicit_provider=explicit_provider, explicit_model=explicit_model, fallback_chain_override=fallback_chain_override)

    def _call_provider_stream(self, decision: RouterDecision, provider: ProviderSpec, messages: List[Dict[str, str]], model_override: Optional[str] = None, timeout_budget: Optional[float] = None) -> Iterator[Dict[str, Any]]:
        import logging
        logging.getLogger(__name__).warning("SEN-MODEL-LEGACY-ROUTER-CALL-STREAM: _call_provider_stream is deprecated, use execute_stream")
        yield from self._provider_manager.execute_inference_stream(decision, provider, messages, model_override=model_override, timeout_budget=timeout_budget)

    def _call_provider(self, decision: RouterDecision, provider: ProviderSpec, messages: List[Dict[str, str]], model_override: Optional[str] = None, timeout: Optional[float] = None, tools: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        import logging
        logging.getLogger(__name__).warning("SEN-MODEL-LEGACY-ROUTER-CALL: _call_provider is deprecated, use execute")
        return self._provider_manager.execute_inference(decision, provider, messages, model_override=model_override, timeout=timeout, tools=tools)

    def _to_legacy_response(self, result: Any, decision: RouterDecision, request) -> Dict[str, Any]:
        """Adapt a canonical InferenceResult to the legacy chat contract."""
        if isinstance(result, dict):
            return {
                "response": result.get("response", ""),
                "selection": {
                    "used": result.get("provider", decision.provider_id),
                    "model": result.get("model", decision.model),
                    "attempt": 1,
                },
                "provider": result.get("provider", decision.provider_id),
                "model": result.get("model", decision.model),
                "usage": result.get("usage", {}),
                "tool_calls": result.get("tool_calls", []),
                "correlation_id": result.get("correlation_id", getattr(request, "correlation_id", "")),
            }
        return {"response": str(result), "provider": decision.provider_id, "model": decision.model, "correlation_id": getattr(request, "correlation_id", "")}

    def chat_with_provider(self, messages: List[Dict[str, str]], provider_id: str, model: str, task_type: TaskType = TaskType.QUICK) -> Dict[str, Any]:
        from sentinel.core.model_schemas import ModelRequest
        provider = self._providers.get(provider_id)
        if not provider:
            raise ValueError(f"Unknown provider: {provider_id}")
        availability = self.provider_availability(provider_id)
        if not availability.available:
            raise RuntimeError(f"Provider '{provider_id}' is unavailable: {availability.reason}")
        request = ModelRequest(
            task_type=task_type.value,
            required_capabilities=["chat"],
            provider_preference=provider_id,
            preferred_model=model,
            context_tokens=sum(len(str(m.get("content", "")).split()) for m in messages),
        )
        decision = self.route(request)
        result = self.execute(request, messages)
        rt_decision = RouterDecision(provider_id=decision.selected_provider, model=decision.selected_model, task_type=task_type, strategy="manual", reason=decision.selection_reason_code)
        return self._to_legacy_response(result, rt_decision, request)

    def check_health(self, provider_id: str, timeout: float = 5.0) -> Dict[str, Any]:
        import httpx
        url = PROVIDER_URLS.get(provider_id)
        if not url:
            return {"provider": provider_id, "available": False, "error": "unknown_provider"}
        try:
            resp = httpx.get(url.rstrip("/v1") if "/v1" in url else url, timeout=timeout, follow_redirects=True)
            return {"provider": provider_id, "available": resp.is_success, "status_code": resp.status_code, "elapsed": resp.elapsed.total_seconds()}
        except Exception as e:
            return {"provider": provider_id, "available": False, "error": str(e)[:100]}

    def chat_with_decision(self, messages: List[Dict[str, str]], decision: Any, task_type: TaskType = TaskType.QUICK) -> Dict[str, Any]:
        from sentinel.core.intelligence_orchestrator import IntelligenceDecision
        if isinstance(decision, IntelligenceDecision):
            return self.chat(messages, task_type=task_type, context={"intent": decision.to_dict()})
        if isinstance(decision, dict):
            return self.chat(messages, task_type=task_type, context={"decision": decision})
        return self.chat(messages, task_type=task_type)

    def chat_with_conversation(self, user_message: str, conversation_context: Any, decision: Any, task_type: TaskType = TaskType.QUICK) -> Dict[str, Any]:
        from sentinel.core.conversation_manager import ConversationManager, ConversationContext, ContextPackage
        if isinstance(conversation_context, ConversationContext):
            messages = conversation_context.get_messages() if hasattr(conversation_context, 'get_messages') else []
            messages.append({"role": "user", "content": user_message})
            result = self.chat(messages, task_type=task_type, context={"conversation": conversation_context.to_dict() if hasattr(conversation_context, 'to_dict') else {}})
            if hasattr(conversation_context, 'add_message'):
                content = result.get("response", "")
                conversation_context.add_message("user", user_message)
                conversation_context.add_message("assistant", content)
            return result
        messages = [{"role": "user", "content": user_message}]
        return self.chat(messages, task_type=task_type)

    @property
    def _circuit_breaker(self):
        return self._cb_store

    @_circuit_breaker.setter
    def _circuit_breaker(self, value):
        self._cb_store = value
        if hasattr(self, '_fallback_manager'):
            self._fallback_manager.set_circuit_breaker(value)

    @property
    def circuit_breaker(self):
        return self._cb_store

    def list_providers(self) -> List[Dict[str, Any]]:
        result = []
        for pid, p in self._providers.items():
            avail = self.provider_availability(pid)
            cb_state = self._cb_store.get_state(pid) if hasattr(self._cb_store, 'get_state') else "closed"
            result.append({
                "id": p.id, "name": p.name, "task_types": [t.value for t in p.task_types],
                "requires_key": p.requires_key, "is_local": p.is_local,
                "default_model": p.default_model, "priority": p.priority,
                "available": avail.available, "reason": avail.reason,
                "circuit_breaker": cb_state,
            })
        return result

    def get_routing_config(self) -> Dict[str, Any]:
        return {
            "strategy": self._strategy,
            "preferred_provider": self._preferred_provider,
            "offline_mode": self._offline_mode,
            "fallback_strategy": self._fallback_strategy,
            "max_fallbacks": self._max_fallbacks,
            "default_fallback_chain": list(self._default_fallback_chain),
            "providers": list(self._providers.keys()),
            "routing_history_size": len(self._routing_history),
            "fallback_stats": self._fallback_stats,
        }
