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

        from sentinel.core.hardware_intelligence import ModelCapabilityManager, get_model_capabilities
        from sentinel.core.model_registry import ModelRegistry, TASK_CAPABILITY_MAP
        from sentinel.core.circuit_breaker import CircuitBreaker

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
                result = self._call_provider(decision, provider, current_messages, model_override=model_override, tools=openai_tools)
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

    def set_circuit_breaker(self, cb) -> None:
        self._cb_store = cb
        self._fallback_manager.set_circuit_breaker(cb)

    def _filter_open_providers(self, candidates: List[RouterDecision]) -> List[RouterDecision]:
        return self._fallback_manager.filter_open_providers(candidates)

    def chat(self, messages: List[Dict[str, str]], task_type: TaskType = TaskType.QUICK, model_override: Optional[str] = None, context: Optional[Dict[str, Any]] = None, fallback_chain_override: Optional[List[str]] = None) -> Dict[str, Any]:
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
                result = self._call_provider(
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

    def chat_stream(self, messages: List[Dict[str, str]], task_type: TaskType = TaskType.QUICK, model_override: Optional[str] = None, context: Optional[Dict[str, Any]] = None, explicit_provider: Optional[str] = None, explicit_model: Optional[str] = None) -> Iterator[Dict[str, Any]]:
        context = context or {}
        routing_start = time.monotonic()
        decision = self.select(task_type, context=context, explicit_provider=explicit_provider, explicit_model=explicit_model)
        candidates = self._filter_open_providers(self._build_fallback_chain(decision, task_type, context=context))
        routing_end = time.monotonic()
        routing_ms = (routing_end - routing_start) * 1000
        logger.info(f"[TIMING] Router Selection: {routing_ms:.2f}ms, Provider: {decision.provider_id}")
        
        if not candidates:
            raise RuntimeError(f"All providers unavailable for {task_type.value}")
        primary_id = candidates[0].provider_id
        last_error: Optional[str] = None
        start_time = time.monotonic()
        offline_fallback_happened = False
        budget_remaining = TOTAL_TIMEOUT_BUDGET
        
        # Count tokens in messages with graceful fallback
        input_tokens = None
        token_counting_method = "exact"
        try:
            import tiktoken
            encoder = tiktoken.get_encoding("cl100k_base")
            input_tokens = sum(len(encoder.encode(str(msg.get("content", "")))) for msg in messages)
            logger.info(f"[TIMING] Input Tokens: {input_tokens} (exact), Messages: {len(messages)}")
        except ImportError:
            # Fallback to heuristic token counting
            token_counting_method = "estimated"
            input_tokens = sum((len(str(msg.get("content", ""))) + 3) // 4 for msg in messages)
            logger.info(f"[TIMING] Input Tokens: {input_tokens} (estimated, tiktoken unavailable), Messages: {len(messages)}")
        except Exception as e:
            # Fallback to heuristic token counting on any error
            token_counting_method = "estimated"
            input_tokens = sum((len(str(msg.get("content", ""))) + 3) // 4 for msg in messages)
            logger.info(f"[TIMING] Input Tokens: {input_tokens} (estimated, tiktoken error: {e}), Messages: {len(messages)}")
        
        safe_trace = {k: v for k, v in (decision.selection_trace or {}).items() if k in {
            "strategy", "eligible", "excluded", "resource_rejections", "resource_score_components",
            "snapshot_summary", "preferred_rejection", "offline_reason",
            "requested_provider", "requested_model", "actual_provider", "actual_model",
        }}
        correlation_id = (context or {}).get("correlation_id") or str(uuid.uuid4())

        for index, candidate in enumerate(candidates):
            provider = self._providers.get(candidate.provider_id)
            if provider is None:
                continue
            elapsed = time.monotonic() - start_time
            remaining = max(10.0, budget_remaining - elapsed)
            emitted_content = False
            is_offline_fallback = candidate.provider_id != primary_id and self._offline_reason is not None and provider.is_local and not offline_fallback_happened
            if is_offline_fallback:
                offline_fallback_happened = True
                yield {"type": "offline_fallback", "primary": primary_id, "used": candidate.provider_id, "reason": self._offline_reason, "explanation": f"Internet no disponible ({self._offline_reason}). Usando modelo local ({candidate.provider_id}) como fallback."}
            is_fallback = candidate.provider_id != decision.provider_id
            fallback_reason = None
            if is_fallback:
                fallback_reason = last_error or candidate.reason or "fallback"
            yield {
                "type": "meta",
                "provider": candidate.provider_id,
                "model": model_override or candidate.model,
                "requested_provider": decision.provider_id,
                "requested_model": decision.model,
                "actual_provider": candidate.provider_id,
                "actual_model": model_override or candidate.model,
                "strategy": decision.strategy,
                "fallback_required": is_fallback,
                "fallback_reason": fallback_reason,
                "selection_trace": safe_trace,
                "route": "conversation",
                "correlation_id": correlation_id,
                "token_counting_method": token_counting_method,
                "input_tokens": input_tokens,
                "routing_ms": routing_ms,
            }
            try:
                for chunk in self._call_provider_stream(candidate, provider, messages, model_override, timeout_budget=remaining):
                    if chunk["type"] == "delta" and chunk.get("text"):
                        emitted_content = True
                    yield chunk
                self._cb_store.record_success(candidate.provider_id)
                if candidate.provider_id != primary_id:
                    self._record_fallback(candidate.provider_id, "success_after_fallback")
                return
            except Exception as e:
                classification = classify_provider_error(e, candidate.provider_id) if not emitted_content else {"category": "stream_interrupted", "message": str(e)}
                last_error = f"[{classification['category']}] {classification['message']}"
                self._cb_store.record_failure(candidate.provider_id)
                if emitted_content:
                    yield {"type": "error", "category": "stream_interrupted", "message": f"Provider {candidate.provider_id} interrupted the response"}
                    return
                continue
        raise RuntimeError(f"All providers failed for {task_type.value}. Last: {last_error}. Elapsed: {format_elapsed(time.monotonic() - start_time)}")

    def _call_provider_stream(self, decision: RouterDecision, provider: ProviderSpec, messages: List[Dict[str, str]], model_override: Optional[str] = None, timeout_budget: Optional[float] = None) -> Iterator[Dict[str, Any]]:
        yield from self._provider_manager.call_provider_stream(decision, provider, messages, model_override=model_override, timeout_budget=timeout_budget)

    def _call_provider(self, decision: RouterDecision, provider: ProviderSpec, messages: List[Dict[str, str]], model_override: Optional[str] = None, timeout: Optional[float] = None, tools: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        return self._provider_manager.call_provider(decision, provider, messages, model_override=model_override, timeout=timeout, tools=tools)

    def chat_with_provider(self, messages: List[Dict[str, str]], provider_id: str, model: str, task_type: TaskType = TaskType.QUICK) -> Dict[str, Any]:
        provider = self._providers.get(provider_id)
        if not provider:
            raise ValueError(f"Unknown provider: {provider_id}")
        availability = self.provider_availability(provider_id)
        if not availability.available:
            raise RuntimeError(f"Provider '{provider_id}' is unavailable: {availability.reason}")
        decision = RouterDecision(provider_id=provider_id, model=model, task_type=task_type, strategy="manual", reason=f"Direct call to {provider_id}/{model}")
        return self._call_provider(decision, provider, messages)

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
