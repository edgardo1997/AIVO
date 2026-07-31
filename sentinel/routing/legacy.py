from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, Iterator, List, Optional
import logging
import os
import time

from .circuit_breaker import CircuitBreaker
from .hardware_intelligence import HardwareProfile, ModelCapabilityManager, get_model_capabilities
from .provider_health import HealthState
from .model_registry import ModelRegistry, TASK_CAPABILITY_MAP
from .tool_schema_adapter import to_openai_tools, parse_tool_call, build_assistant_tool_message, build_tool_result_message, build_tool_error_message
from sentinel.models import ModelMetadata

logger = logging.getLogger(__name__)


class TaskType(Enum):
    REASONING = "reasoning"
    ANALYSIS = "analysis"
    QUICK = "quick"
    CODE = "code"
    CREATIVE = "creative"
    LOCAL = "local"


@dataclass
class ProviderSpec:
    id: str
    name: str
    task_types: List[TaskType]
    requires_key: bool = True
    is_local: bool = False
    default_model: str = ""
    priority: int = 10
    config: Dict[str, Any] = field(default_factory=dict)
    fallback_chain: List[str] = field(default_factory=list)


BUILTIN_PROVIDERS = [
    ProviderSpec(
        id="deepseek",
        name="DeepSeek v4 Flash (Free)",
        task_types=[TaskType.REASONING, TaskType.CODE, TaskType.QUICK, TaskType.ANALYSIS, TaskType.CREATIVE],
        requires_key=True,
        default_model="deepseek/deepseek-v4-flash:free",
        priority=10,
        config={"base_url": "https://api.deepseek.com/v1"},
        fallback_chain=["nvidia", "sentinel_local"],
    ),
    ProviderSpec(
        id="nvidia-nemotron",
        name="NVIDIA Nemotron (Free)",
        task_types=[TaskType.REASONING, TaskType.CODE, TaskType.QUICK, TaskType.ANALYSIS],
        requires_key=True,
        default_model="nvidia/nemotron-3-super-120b-a12b",
        priority=20,
        config={"base_url": "https://integrate.api.nvidia.com/v1"},
        fallback_chain=["sentinel_local"],
    ),
    ProviderSpec(
        id="openrouter",
        name="OpenRouter",
        task_types=[TaskType.REASONING, TaskType.ANALYSIS, TaskType.QUICK, TaskType.CODE, TaskType.CREATIVE],
        requires_key=True,
        default_model="deepseek/deepseek-v4-flash:free",
        priority=30,
    ),
    ProviderSpec(
        id="groq",
        name="Groq",
        task_types=[TaskType.QUICK, TaskType.ANALYSIS],
        requires_key=True,
        default_model="llama-3.3-70b-versatile",
        priority=25,
    ),
    ProviderSpec(
        id="gemini",
        name="Gemini",
        task_types=[TaskType.REASONING, TaskType.ANALYSIS, TaskType.CREATIVE],
        requires_key=True,
        default_model="gemini-2.5-flash",
        priority=18,
    ),
    ProviderSpec(
        id="github_models",
        name="GitHub Models (Free)",
        task_types=[TaskType.QUICK, TaskType.CODE, TaskType.REASONING, TaskType.ANALYSIS],
        requires_key=True,
        default_model="gpt-4o",
        priority=12,
        config={"base_url": "https://models.inference.ai.azure.com"},
        fallback_chain=["sentinel_local"],
    ),
    ProviderSpec(
        id="openai",
        name="OpenAI",
        task_types=[TaskType.REASONING, TaskType.CODE, TaskType.CREATIVE],
        requires_key=True,
        default_model="gpt-4o",
        priority=22,
    ),
    ProviderSpec(
        id="anthropic",
        name="Anthropic",
        task_types=[TaskType.REASONING, TaskType.ANALYSIS, TaskType.CODE],
        requires_key=True,
        default_model="claude-sonnet-4",
        priority=22,
    ),
    ProviderSpec(
        id="sentinel_local",
        name="Sentinel Local",
        task_types=[
            TaskType.LOCAL,
            TaskType.QUICK,
            TaskType.REASONING,
            TaskType.ANALYSIS,
            TaskType.CODE,
            TaskType.CREATIVE,
        ],
        requires_key=False,
        is_local=True,
        default_model="Qwen3-1.7B-Q8_0.gguf",
        priority=50,  # Prioridad más baja - último fallback
        config={"hardware": {"working_set_gb": 3.0, "minimum_cpu_cores": 2}},
    ),
    ProviderSpec(
        id="ollama",
        name="Ollama",
        task_types=[TaskType.LOCAL, TaskType.QUICK],
        requires_key=False,
        is_local=True,
        default_model="llama3",
        priority=30,
        config={"hardware": {"working_set_gb": 6.0, "minimum_cpu_cores": 4}},
    ),
    ProviderSpec(
        id="cerebras",
        name="Cerebras",
        task_types=[TaskType.QUICK, TaskType.ANALYSIS],
        requires_key=True,
        default_model="llama-3.3-70b",
        priority=14,
    ),
    ProviderSpec(
        id="mistral",
        name="Mistral",
        task_types=[TaskType.REASONING, TaskType.CODE, TaskType.ANALYSIS],
        requires_key=True,
        default_model="mistral-large-latest",
        priority=16,
    ),
    ProviderSpec(
        id="nvidia",
        name="NVIDIA NIM",
        task_types=[TaskType.REASONING, TaskType.ANALYSIS, TaskType.QUICK, TaskType.CODE, TaskType.CREATIVE],
        requires_key=True,
        default_model="nvidia/nemotron-3-super-120b-a12b",
        priority=28,
    ),
]

ROUTING_STRATEGIES = ["priority", "cost", "local_first", "smart", "manual"]
OFFLINE_MODES = ["off", "auto", "force_local"]

PROVIDER_URLS: Dict[str, str] = {
    "openrouter": "https://openrouter.ai/api/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "groq": "https://api.groq.com/openai/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "github_models": "https://models.inference.ai.azure.com",
    "cerebras": "https://api.cerebras.ai/v1",
    "mistral": "https://api.mistral.ai/v1",
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com/v1",
    "nvidia": "https://integrate.api.nvidia.com/v1",
    "nvidia-nemotron": "https://integrate.api.nvidia.com/v1",
    "sentinel_local": "http://127.0.0.1:11435/v1",
    "ollama": "http://localhost:11434/v1",
}

SYSTEM_PROMPT_DEFAULT = (
    "You are an AI assistant integrated into AIVO, a desktop productivity tool. "
    "Your purpose is to help the user with system monitoring, file management, task "
    "execution, and general computer assistance. Be concise, accurate, and helpful."
)


@dataclass
class RouterDecision:
    provider_id: str
    model: str
    task_type: TaskType
    strategy: str
    reason: str
    selection_trace: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data = {
            "provider_id": self.provider_id,
            "model": self.model,
            "task_type": self.task_type.value,
            "strategy": self.strategy,
            "reason": self.reason,
        }
        if self.selection_trace:
            data["selection_trace"] = self.selection_trace
        return data


@dataclass
class ProviderAvailability:
    provider_id: str
    available: bool
    reason: str
    checked_at: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "available": self.available,
            "reason": self.reason,
            "checked_at": self.checked_at,
        }


FALLBACK_STRATEGIES = ["chain", "round_robin", "broadcast"]

# ── Timeout constants (seconds) ──────────────────────────────────────────
# Total wall-clock budget across all fallback attempts.
TOTAL_TIMEOUT_BUDGET = 120.0
# Per-candidate timeouts for streaming.
CONNECT_TIMEOUT = 10.0
FIRST_TOKEN_TIMEOUT_NONLOCAL = 30.0
FIRST_TOKEN_TIMEOUT_LOCAL = 60.0
STREAM_IDLE_TIMEOUT = 20.0
# Non-streaming per-provider call timeout.
CALL_TIMEOUT = 60.0
LOCAL_CALL_TIMEOUT = 90.0


def classify_provider_error(exception: Exception, provider_id: str) -> Dict[str, Any]:
    """Classify an error from a provider call into a structured category."""
    msg = str(exception)
    cls = type(exception).__name__

    # OpenAI / httpx specific errors
    if hasattr(exception, "status_code"):
        code = exception.status_code
    elif hasattr(exception, "response") and hasattr(exception.response, "status_code"):
        code = exception.response.status_code
    else:
        code = None

    if code == 401 or "401" in msg or "unauthorized" in msg.lower() or "invalid_api_key" in msg.lower():
        return {"category": "invalid_auth", "status_code": 401, "message": "Invalid or missing API key"}
    if code == 403 or "403" in msg or "forbidden" in msg.lower():
        return {
            "category": "invalid_auth",
            "status_code": 403,
            "message": "API key lacks access to the requested model",
        }
    if code == 429 or "429" in msg or "rate limit" in msg.lower() or "too many requests" in msg.lower():
        return {"category": "rate_limited", "status_code": 429, "message": "Rate limited by provider"}
    if code == 404 or "404" in msg or "model not found" in msg.lower():
        return {"category": "model_not_found", "status_code": 404, "message": f"Model not available: {msg}"}
    if isinstance(exception, TimeoutError) or "timeout" in cls.lower() or "timed out" in msg.lower():
        return {"category": "timeout", "status_code": None, "message": "Provider did not respond in time"}
    if "name or service not known" in msg.lower() or "no address associated" in msg.lower() or "dns" in msg.lower():
        return {"category": "dns_failure", "status_code": None, "message": "Cannot resolve provider hostname"}
    if "connection refused" in msg.lower() or "connection error" in msg.lower() or "connection reset" in msg.lower():
        return {"category": "connection_failure", "status_code": None, "message": "Connection refused or reset"}
    if "model_not_found" in cls.lower() or "model not found" in msg.lower():
        return {"category": "model_not_found", "status_code": 404, "message": f"Model not available: {msg}"}
    if code and 500 <= code < 600:
        return {"category": "server_error", "status_code": code, "message": f"Provider server error ({code})"}
    if "insufficient_quota" in msg.lower() or "quota" in msg.lower() or "exceeded" in msg.lower():
        return {"category": "no_quota", "status_code": 403, "message": "API quota exhausted"}

    return {"category": "unknown", "status_code": code, "message": msg}


def format_elapsed(seconds: float) -> str:
    if seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    return f"{seconds:.1f}s"


class ModelRouter:
    def __init__(
        self,
        providers: Optional[List[ProviderSpec]] = None,
        default_fallback_chain: Optional[List[str]] = None,
        fallback_strategy: str = "chain",
        max_fallbacks: int = 5,
        availability_checker: Optional[Callable[[ProviderSpec], ProviderAvailability]] = None,
        availability_ttl_seconds: float = 15.0,
        capability_manager: Optional[ModelCapabilityManager] = None,
    ):
        self._providers: Dict[str, ProviderSpec] = {}
        self._key_map: Dict[str, str] = {}
        self._strategy: str = "priority"
        self._preferred_provider: Optional[str] = None
        self._db = None
        self._feedback_store = None
        self._cost_tracker = None
        self._circuit_breaker = CircuitBreaker()
        self._default_fallback_chain: List[str] = default_fallback_chain or []
        self._fallback_strategy: str = fallback_strategy if fallback_strategy in FALLBACK_STRATEGIES else "chain"
        self._max_fallbacks: int = max_fallbacks
        self._fallback_stats: Dict[str, int] = {}  # provider_id -> fallback count
        self._fallback_history: List[Dict[str, Any]] = []
        self._availability_checker = availability_checker
        self._availability_ttl_seconds = max(0.0, availability_ttl_seconds)
        self._availability_cache: Dict[str, ProviderAvailability] = {}
        self._routing_history: List[Dict[str, Any]] = []
        self._task_type_map: Dict[TaskType, str] = {}
        self._capability_manager = capability_manager or get_model_capabilities()
        self._offline_mode: str = "auto"
        self._health_checker = None
        self._offline_reason: Optional[str] = None
        self._model_registry: Optional[ModelRegistry] = None
        self._tool_gateway: Any = None
        self._tool_guard: Any = None
        self._tool_calling_max_recursion: int = 5
        self._task_capability_map: Dict[TaskType, List[str]] = {
            TaskType.CODE: TASK_CAPABILITY_MAP.get("coding", []),
            TaskType.REASONING: TASK_CAPABILITY_MAP.get("reasoning", []),
            TaskType.ANALYSIS: TASK_CAPABILITY_MAP.get("analysis", []),
            TaskType.QUICK: [],
            TaskType.CREATIVE: [],
            TaskType.LOCAL: TASK_CAPABILITY_MAP.get("local", []),
        }

        for p in BUILTIN_PROVIDERS if providers is None else providers:
            self._providers[p.id] = p

    def set_feedback_store(self, store: Any) -> None:
        self._feedback_store = store

    def set_cost_tracker(self, tracker: Any) -> None:
        self._cost_tracker = tracker

    def set_database(self, db: Any) -> None:
        self._db = db

    def load_keys_from_db(self) -> None:
        pass

    def save_keys_to_db(self) -> None:
        pass

    def set_api_key(self, provider_id: str, key: str) -> None:
        if provider_id not in self._providers:
            raise KeyError(f"Provider '{provider_id}' not found")
        self._key_map[provider_id] = key
        self._availability_cache.pop(provider_id, None)

    def delete_api_key(self, provider_id: str) -> bool:
        if provider_id not in self._providers:
            return False
        removed = self._key_map.pop(provider_id, None)
        self._availability_cache.pop(provider_id, None)
        return removed is not None

    def has_api_key(self, provider_id: str) -> bool:
        spec = self._providers.get(provider_id)
        if spec is None:
            return False
        if not spec.requires_key:
            return True
        return provider_id in self._key_map and bool(self._key_map[provider_id])

    def provider_availability(self, provider_id: str, refresh: bool = False) -> ProviderAvailability:
        provider = self._providers.get(provider_id)
        now = time.time()
        if provider is None:
            return ProviderAvailability(provider_id, False, "unknown_provider", now)
        if provider_id == "sentinel_local" and os.environ.get("SENTINEL_DISABLE_LOCAL_AI") == "1":
            return ProviderAvailability(provider_id, False, "disabled_by_environment", now)
        cached = self._availability_cache.get(provider_id)
        if not refresh and cached and now - cached.checked_at < self._availability_ttl_seconds:
            return cached
        if provider.requires_key and not self.has_api_key(provider_id):
            result = ProviderAvailability(provider_id, False, "missing_api_key", now)
        elif provider.is_local:
            if self._availability_checker:
                result = self._availability_checker(provider)
            else:
                health = self.check_health(provider_id, timeout=0.75)
                result = ProviderAvailability(
                    provider_id,
                    bool(health.get("available")),
                    "local_service_reachable"
                    if health.get("available")
                    else health.get("error", "local_service_unreachable"),
                    now,
                )
        else:
            result = ProviderAvailability(provider_id, True, "api_key_configured", now)
        self._availability_cache[provider_id] = result
        return result

    def availability_snapshot(self, refresh: bool = False) -> Dict[str, Dict[str, Any]]:
        return {
            provider_id: self.provider_availability(provider_id, refresh=refresh).to_dict()
            for provider_id in self._providers
        }

    def routing_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        return list(self._routing_history[-max(1, limit) :])

    def _record_decision(self, decision: RouterDecision) -> RouterDecision:
        self._routing_history.append({"timestamp": time.time(), **decision.to_dict()})
        if len(self._routing_history) > 500:
            del self._routing_history[:-500]
        return decision

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

    def get_offline_mode(self) -> str:
        return self._offline_mode

    def set_health_checker(self, checker) -> None:
        self._health_checker = checker

    def is_offline(self) -> bool:
        if self._offline_mode == "force_local":
            self._offline_reason = "offline_mode_forced"
            return True
        if self._offline_mode == "off":
            self._offline_reason = None
            return False
        if self._health_checker is not None:
            offline = not self._health_checker.internet_online
            if offline:
                self._offline_reason = "no_internet"
            else:
                self._offline_reason = None
            return offline
        return False

    def set_default_fallback_chain(self, chain: List[str]) -> None:
        self._default_fallback_chain = chain

    def set_fallback_strategy(self, strategy: str) -> None:
        if strategy not in FALLBACK_STRATEGIES:
            raise ValueError(f"Fallback strategy must be one of {FALLBACK_STRATEGIES}")
        self._fallback_strategy = strategy

    def set_max_fallbacks(self, n: int) -> None:
        self._max_fallbacks = max(1, n)

    def set_task_type_map(self, mapping: Dict[TaskType, str]) -> None:
        self._task_type_map = dict(mapping)

    def set_task_type_map_from_dict(self, mapping: Dict[str, str]) -> None:
        resolved = {}
        for k, v in mapping.items():
            try:
                resolved[TaskType(k)] = v
            except ValueError:
                logger.warning("Ignoring unknown task type '%s' in task_type_map", k)
        self._task_type_map = resolved

    def set_model_registry(self, registry: ModelRegistry) -> None:
        self._model_registry = registry
        logger.info("ModelRouter: ModelRegistry attached with %d models", registry.count())

    def set_tool_gateway(self, gateway: Any) -> None:
        self._tool_gateway = gateway

    def set_tool_guard(self, guard: Any) -> None:
        self._tool_guard = guard
        # Sync gateway if guard has set_tool_gateway
        if hasattr(guard, "set_tool_gateway") and self._tool_gateway:
            guard.set_tool_gateway(self._tool_gateway)

    def set_task_capability_map(self, task_type: TaskType, capabilities: List[str]) -> None:
        self._task_capability_map[task_type] = list(capabilities)

    def select_by_capability(
        self,
        required_capabilities: List[str],
        task_type: Optional[TaskType] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Optional[RouterDecision]:
        if self._model_registry is None:
            logger.warning("ModelRegistry not set — falling back to provider-based selection")
            return None
        candidates = self._model_registry.find_candidates(required_capabilities)
        if not candidates:
            return None
        strategy = self._strategy
        if strategy == "local_first":
            candidates.sort(key=lambda m: (not m.local, m.cost))
        elif strategy == "cost":
            candidates.sort(key=lambda m: (m.cost, m.local))
        else:
            candidates.sort(key=lambda m: (m.cost, m.local))
        best = candidates[0]
        return RouterDecision(
            provider_id=best.provider,
            model=best.id,
            task_type=task_type or TaskType.QUICK,
            strategy=f"capability_{strategy}",
            reason=f"Selected {best.id} via capability filter: {required_capabilities}",
        )

    def _validate_tool_call_compatibility(self, model_id: str, provider_id: str) -> bool:
        if self._model_registry is None:
            return True
        model = self._model_registry.get(model_id)
        if model is None:
            return True
        if not model.supports_tool_calling:
            logger.error(
                "Tool calling rejected: model '%s' (provider=%s) has supports_tool_calling=False",
                model_id, provider_id,
            )
            return False
        return True

    async def _execute_tool_call_safe(
        self, tool_call: Dict[str, Any], provider_id: str, model_id: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Ejecuta un tool call a través del ToolExecutionGuard.

        El ModelRouter ya no ejecuta herramientas directamente.
        Crea un ToolRequest y delega en el guard para todas las
        comprobaciones de seguridad.
        """
        from sentinel.security.models import ToolRequest

        tool_name = tool_call["function"]["name"]
        arguments = tool_call["function"]["arguments"]
        tool_call_id = tool_call["id"]

        if self._tool_guard is None:
            logger.error(
                "ToolExecutionGuard not configured — rejecting tool '%s' execution",
                tool_name,
            )
            return build_tool_error_message(
                tool_call_id, tool_name,
                "ToolExecutionGuard not configured — execution rejected",
            )

        user_context = dict(context or {})
        user_context["source"] = "model_router"
        user_context["provider_id"] = provider_id
        user_context["model_id"] = model_id

        request = ToolRequest(
            tool_name=tool_name,
            arguments=arguments,
            source=f"model:{model_id}/provider:{provider_id}",
            user_context=user_context,
            session_id=user_context.get("session_id", ""),
            user_id=user_context.get("user_id", ""),
            execution_id=user_context.get("execution_id", ""),
            model_id=model_id,
            provider_id=provider_id,
        )

        guard_result = await self._tool_guard.execute(request)
        if guard_result.success:
            return build_tool_result_message(tool_call_id, tool_name, guard_result.data)
        return build_tool_error_message(tool_call_id, tool_name, guard_result.error or "Blocked by ToolExecutionGuard")

    async def _handle_tool_calls(
        self,
        tool_calls: List[Dict[str, Any]],
        provider_id: str,
        model_id: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        if not self._validate_tool_call_compatibility(model_id, provider_id):
            raise RuntimeError(
                f"Tool calling rejected: model '{model_id}' (provider={provider_id}) "
                f"does not support tool calling"
            )
        tool_result_messages = []
        for tc in tool_calls:
            tool_name = tc["function"]["name"]
            logger.info(
                "Tool call: model=%s tool=%s args=%s",
                model_id, tool_name, tc["function"]["arguments"],
            )
            msg = await self._execute_tool_call_safe(tc, provider_id, model_id, context=context)
            tool_result_messages.append(msg)
        return tool_result_messages

    async def chat_with_tools(
        self,
        messages: List[Dict[str, str]],
        tools: List[Any],
        task_type: TaskType = TaskType.QUICK,
        model_override: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        max_tool_rounds: int = 5,
    ) -> Dict[str, Any]:
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
            result = self._call_provider(
                decision, provider, current_messages,
                model_override=model_override,
                tools=openai_tools,
            )
            elapsed = time.monotonic() - elapsed
            total_elapsed += elapsed

            tool_calls = result.get("tool_calls", [])
            content = result.get("response")

            if not tool_calls:
                last_response = result
                last_response["tool_calling_rounds"] = round_idx
                last_response["total_elapsed_seconds"] = total_elapsed
                return last_response

            try:
                tool_msgs = await self._handle_tool_calls(
                    tool_calls, decision.provider_id, model_id, context=context
                )
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
        return {
            "strategy": self._fallback_strategy,
            "max_fallbacks": self._max_fallbacks,
            "default_chain": list(self._default_fallback_chain),
            "fallback_counts": dict(self._fallback_stats),
            "total_fallbacks": sum(self._fallback_stats.values()),
            "recent_history": self._fallback_history[-20:],
        }

    def reset_fallback_stats(self) -> int:
        count = sum(self._fallback_stats.values())
        self._fallback_stats.clear()
        self._fallback_history.clear()
        return count

    def _build_fallback_chain(
        self,
        primary: RouterDecision,
        task_type: TaskType,
        context: Optional[Dict[str, Any]] = None,
    ) -> List[RouterDecision]:
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
                    if not self.provider_availability(pid).available:
                        continue
                    result.append(
                        RouterDecision(
                            provider_id=pid,
                            model=spec.default_model,
                            task_type=task_type,
                            strategy=self._strategy,
                            reason=f"Fallback chain: {pid}",
                        )
                    )
                    seen.add(pid)
                if len(result) - 1 >= self._max_fallbacks:
                    break
            return result

        all_candidates = self.select_all(task_type, context=context)
        result = [primary]
        seen = {primary.provider_id}
        for c in all_candidates:
            if c.provider_id not in seen:
                result.append(c)
                seen.add(c.provider_id)
            if len(result) - 1 >= self._max_fallbacks:
                break
        return result

    def _record_fallback(self, provider_id: str, category: str = "unknown") -> None:
        self._fallback_stats[provider_id] = self._fallback_stats.get(provider_id, 0) + 1

    def _try_select_from_registry(
        self, task_type: TaskType, context: Optional[Dict[str, Any]] = None
    ) -> Optional[RouterDecision]:
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
        logger.info(
            "Registry-based selection for %s: %s (caps=%s, strategy=%s)",
            task_type.value, best.id, required_caps, strategy,
        )
        return self._record_decision(
            RouterDecision(
                provider_id=best.provider,
                model=best.id,
                task_type=task_type,
                strategy=f"registry_{strategy}",
                reason=f"Registry: {best.id} matched capabilities {required_caps}",
                selection_trace={
                    "candidates": [m.id for m in candidates],
                    "required_capabilities": required_caps,
                },
            )
        )

    def select(self, task_type: TaskType, context: Optional[Dict[str, Any]] = None) -> RouterDecision:
        registry_decision = self._try_select_from_registry(task_type, context)
        if registry_decision is not None:
            return registry_decision

        logger.debug(
            "Deprecated: provider-based selection for %s — use ModelRegistry for capability-aware routing",
            task_type.value,
        )

        if self._strategy == "smart":
            return self._smart_select(task_type, context or {})

        candidates = self._filter_candidates(task_type, context)
        if not candidates:
            snapshot = {
                provider.id: self._candidate_exclusion_reason(provider, context)
                for provider in self._providers.values()
                if task_type in provider.task_types
            }
            raise RuntimeError(f"No available provider supports task type '{task_type.value}'. Exclusions: {snapshot}")

        if self._preferred_provider:
            candidates.sort(
                key=lambda provider: (
                    provider.id != self._preferred_provider,
                    -provider.priority,
                )
            )
        elif self._strategy == "local_first":
            candidates.sort(key=lambda p: (not p.is_local, -p.priority))
        elif self._strategy == "cost":
            candidates.sort(key=lambda p: (p.requires_key, -p.priority))
        else:
            candidates.sort(key=lambda p: -p.priority)

        best = candidates[0]
        excluded = {
            p.id: self._candidate_exclusion_reason(p, context)
            for p in self._providers.values()
            if task_type in p.task_types and p.id not in {c.id for c in candidates}
        }
        hardware = self._hardware_trace(candidates, context)
        reason = f"Selected {best.id} for {task_type.value} (strategy={self._strategy}, priority={best.priority}, availability=verified)"
        if self._offline_reason:
            reason += f", offline={self._offline_reason}"
        logger.info(reason)

        return self._record_decision(
            RouterDecision(
                provider_id=best.id,
                model=best.default_model,
                task_type=task_type,
                strategy=self._strategy,
                reason=reason,
                selection_trace={
                    "eligible": [p.id for p in candidates],
                    "excluded": excluded,
                    "hardware": hardware,
                    "offline_reason": self._offline_reason,
                },
            )
        )

    def _filter_candidates(self, task_type: TaskType, context: Optional[Dict[str, Any]] = None) -> List[ProviderSpec]:
        offline = self.is_offline()
        return [
            p
            for p in self._providers.values()
            if task_type in p.task_types
            and self.provider_availability(p.id).available
            and self._hardware_allows(p, context)
            and (not offline or p.is_local)
        ]

    @staticmethod
    def _hardware_profile(context: Optional[Dict[str, Any]]) -> Optional[HardwareProfile]:
        if not context:
            return None
        hardware = context.get("hardware")
        if not isinstance(hardware, dict):
            deep = context.get("deep_context")
            hardware = deep.get("hardware") if isinstance(deep, dict) else None
        return HardwareProfile.from_context(hardware) if isinstance(hardware, dict) else None

    def _hardware_assessment(
        self, provider: ProviderSpec, context: Optional[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        if not provider.is_local:
            return None
        profile = self._hardware_profile(context)
        if profile is None:
            return None
        return self._capability_manager.assess(provider.default_model, profile, provider.config).to_dict()

    def _hardware_allows(self, provider: ProviderSpec, context: Optional[Dict[str, Any]]) -> bool:
        assessment = self._hardware_assessment(provider, context)
        return not assessment or assessment.get("compatible") is not False

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
            provider.id: assessment
            for provider in candidates
            if (assessment := self._hardware_assessment(provider, context)) is not None
        }

    def _smart_select(self, task_type: TaskType, context: Dict[str, Any]) -> RouterDecision:
        candidates = self._filter_candidates(task_type, context)
        if not candidates:
            exclusions = {
                provider.id: self._candidate_exclusion_reason(provider, context)
                for provider in self._providers.values()
                if task_type in provider.task_types
            }
            raise RuntimeError(
                f"No available provider supports task type '{task_type.value}'. Exclusions: {exclusions}"
            )

        sys_sum = context.get("system_summary", {}) or {}
        cpu = sys_sum.get("cpu_percent", 50)
        mem = sys_sum.get("memory_percent", 50)
        perm_level = context.get("permission_level", "confirm")
        battery = sys_sum.get("battery", None)

        is_high_load = (isinstance(cpu, (int, float)) and cpu > 80) or (isinstance(mem, (int, float)) and mem > 85)
        is_battery_low = (
            isinstance(battery, dict) and battery.get("percent", 100) < 20 and not battery.get("power_plugged", True)
        )
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
                cost_per_call = self._cost_tracker.get_model_price(p.id, p.default_model)
                if cost_per_call > 0:
                    score -= cost_per_call * 1000

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
        reason = f"Smart-selected {best.id} for {task_type.value} (score={dynamic_score(best):.0f}, {factors})"
        logger.debug(reason)

        return self._record_decision(
            RouterDecision(
                provider_id=best.id,
                model=best.default_model,
                task_type=task_type,
                strategy="smart",
                reason=reason,
                selection_trace={
                    "eligible": [p.id for p in candidates],
                    "score": dynamic_score(best),
                    "hardware": self._hardware_trace(candidates, context),
                },
            )
        )

    def select_all(self, task_type: TaskType, context: Optional[Dict[str, Any]] = None) -> List[RouterDecision]:
        candidates = self._filter_candidates(task_type, context)

        if self._strategy == "smart":
            ctx = context or {}
            sys_sum = ctx.get("system_summary", {}) or {}
            cpu = sys_sum.get("cpu_percent", 50)
            mem = sys_sum.get("memory_percent", 50)
            is_high_load = (isinstance(cpu, (int, float)) and cpu > 80) or (isinstance(mem, (int, float)) and mem > 85)

            def dyn_score(p):
                s = float(p.priority)
                if is_high_load and not p.is_local:
                    s += 10
                if is_high_load and p.is_local:
                    s -= 5
                return s

            candidates.sort(key=dyn_score, reverse=True)
        else:
            if self._strategy == "local_first":
                candidates.sort(key=lambda p: (not p.is_local, -p.priority))
            elif self._strategy == "cost":
                candidates.sort(key=lambda p: (p.requires_key, -p.priority))
            else:
                candidates.sort(key=lambda p: -p.priority)

        return [
            RouterDecision(
                provider_id=p.id,
                model=p.default_model,
                task_type=task_type,
                strategy=self._strategy,
                reason=f"Candidate {p.id} (priority={p.priority})",
            )
            for p in candidates
        ]

    def set_circuit_breaker(self, cb: CircuitBreaker) -> None:
        self._circuit_breaker = cb

    def _filter_open_providers(self, candidates: List[RouterDecision]) -> List[RouterDecision]:
        filtered = []
        for c in candidates:
            if self._circuit_breaker.allow_request(c.provider_id):
                filtered.append(c)
            else:
                logger.info("Circuit breaker OPEN for %s, skipping", c.provider_id)
        return filtered

    def chat(
        self,
        messages: List[Dict[str, str]],
        task_type: TaskType = TaskType.QUICK,
        model_override: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        fallback_chain_override: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        context = context or {}
        decision = self.select(task_type, context=context)

        if fallback_chain_override is not None:
            chain_ids = fallback_chain_override
            chain = [decision]
            seen = {decision.provider_id}
            for pid in chain_ids:
                if pid not in seen and pid in self._providers and self.provider_availability(pid).available:
                    spec = self._providers[pid]
                    chain.append(
                        RouterDecision(
                            provider_id=pid,
                            model=spec.default_model,
                            task_type=task_type,
                            strategy=self._strategy,
                            reason=f"Fallback override: {pid}",
                        )
                    )
                    seen.add(pid)
                if len(chain) - 1 >= self._max_fallbacks:
                    break
        else:
            chain = self._build_fallback_chain(decision, task_type, context=context)

        candidates = self._filter_open_providers(chain)
        last_error: Optional[str] = None
        start_time = time.monotonic()
        budget_remaining = TOTAL_TIMEOUT_BUDGET

        if not candidates:
            states = self._circuit_breaker.get_all_states()
            raise RuntimeError(
                f"All providers unavailable (circuit breaker open) for {task_type.value}. "
                f"States: {[s['provider_id'] + '=' + s['state'] for s in states]}"
            )

        primary_id = candidates[0].provider_id
        for idx, candidate in enumerate(candidates):
            provider = self._providers.get(candidate.provider_id)
            if not provider:
                continue
            elapsed = time.monotonic() - start_time
            remaining = max(5.0, budget_remaining - elapsed)
            per_call_timeout = min(remaining, LOCAL_CALL_TIMEOUT if provider.is_local else CALL_TIMEOUT)
            try:
                result = self._call_provider(
                    candidate,
                    provider,
                    messages,
                    model_override,
                    timeout=per_call_timeout,
                )
                elapsed_total = time.monotonic() - start_time
                self._circuit_breaker.record_success(candidate.provider_id)
                if self._cost_tracker and result.get("usage"):
                    usage = result["usage"]
                    self._cost_tracker.record_cost(
                        provider_id=candidate.provider_id,
                        model=candidate.model,
                        task_type=task_type,
                        prompt_tokens=usage.get("prompt_tokens", 0),
                        completion_tokens=usage.get("completion_tokens", 0),
                    )
                offline_fallback = (
                    candidate.provider_id != primary_id and self._offline_reason is not None and provider.is_local
                )
                result["selection"] = {
                    "primary": primary_id,
                    "used": candidate.provider_id,
                    "model": candidate.model,
                    "strategy": self._strategy,
                    "reason": candidate.reason,
                    "attempt": idx + 1,
                    "total_fallbacks_tried": idx,
                    "elapsed": format_elapsed(elapsed_total),
                }
                if offline_fallback:
                    result["selection"]["offline_fallback"] = True
                    result["selection"]["offline_reason"] = self._offline_reason
                    result["selection"]["fallback_explanation"] = (
                        f"Internet no disponible ({self._offline_reason}). "
                        f"Usando modelo local ({candidate.provider_id}) como fallback."
                    )
                if candidate.provider_id != primary_id:
                    self._record_fallback(candidate.provider_id, "success_after_fallback")
                    self._fallback_history.append(
                        {
                            "primary": primary_id,
                            "used": candidate.provider_id,
                            "model": candidate.model,
                            "attempt": idx + 1,
                            "elapsed": elapsed_total,
                            "category": "success_after_fallback",
                        }
                    )
                logger.info(
                    "Chat success: provider=%s model=%s attempt=%d/%d elapsed=%s",
                    candidate.provider_id,
                    candidate.model,
                    idx + 1,
                    len(candidates),
                    format_elapsed(elapsed_total),
                )
                return result
            except Exception as e:
                classification = classify_provider_error(e, candidate.provider_id)
                last_error = f"[{classification['category']}] {classification['message']}"
                self._circuit_breaker.record_failure(candidate.provider_id)
                self._fallback_history.append(
                    {
                        "primary": primary_id,
                        "used": candidate.provider_id,
                        "attempt": idx + 1,
                        "category": classification.get("category", "unknown"),
                        "message": classification.get("message", ""),
                        "elapsed": time.monotonic() - start_time,
                    }
                )
                logger.warning(
                    "Provider %s failed (attempt %d/%d, budget_remaining=%.0fs): [%s] %s",
                    candidate.provider_id,
                    idx + 1,
                    len(candidates),
                    remaining,
                    classification["category"],
                    classification["message"],
                )
                if remaining < 5.0 and idx < len(candidates) - 1:
                    logger.warning("Timeout budget exhausted, stopping fallback chain")
                    break
                continue

        raise RuntimeError(
            f"All providers failed for {task_type.value}. "
            f"Last: {last_error}. Elapsed: {format_elapsed(time.monotonic() - start_time)}"
        )

    def chat_stream(
        self,
        messages: List[Dict[str, str]],
        task_type: TaskType = TaskType.QUICK,
        model_override: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Iterator[Dict[str, Any]]:
        """Yield provider metadata and model deltas without bypassing routing policy.

        Fallback is allowed until a provider emits content. Once content reaches
        the caller, switching providers would create a misleading mixed answer,
        so a mid-stream failure is reported explicitly instead.

        Timeouts: total budget across all fallbacks; separate connect, first-token
        and stream-idle timeouts within each provider.
        """
        context = context or {}
        decision = self.select(task_type, context=context)
        candidates = self._filter_open_providers(self._build_fallback_chain(decision, task_type, context=context))
        if not candidates:
            raise RuntimeError(f"All providers unavailable for {task_type.value}")

        primary_id = candidates[0].provider_id
        last_error: Optional[str] = None
        last_classification: Optional[Dict[str, Any]] = None
        start_time = time.monotonic()
        budget_remaining = TOTAL_TIMEOUT_BUDGET

        offline_fallback_happened = False
        for index, candidate in enumerate(candidates):
            provider = self._providers.get(candidate.provider_id)
            if provider is None:
                continue
            elapsed = time.monotonic() - start_time
            remaining = max(10.0, budget_remaining - elapsed)
            emitted_content = False
            is_offline_fallback = (
                candidate.provider_id != primary_id
                and self._offline_reason is not None
                and provider.is_local
                and not offline_fallback_happened
            )
            if is_offline_fallback:
                offline_fallback_happened = True
                yield {
                    "type": "offline_fallback",
                    "primary": primary_id,
                    "used": candidate.provider_id,
                    "reason": self._offline_reason,
                    "explanation": (
                        f"Internet no disponible ({self._offline_reason}). "
                        f"Usando modelo local ({candidate.provider_id}) como fallback."
                    ),
                }
            try:
                stream_events: List[Dict[str, Any]] = []
                for event in self._call_provider_stream(
                    candidate,
                    provider,
                    messages,
                    model_override,
                    timeout_budget=remaining,
                ):
                    if event["type"] == "delta" and event.get("text"):
                        emitted_content = True
                    stream_events.append(event)
                    yield event
                self._circuit_breaker.record_success(candidate.provider_id)
                metrics = next((e for e in stream_events if e["type"] == "metrics"), None)
                if self._cost_tracker and metrics:
                    self._cost_tracker.record_cost(
                        provider_id=candidate.provider_id,
                        model=candidate.model,
                        task_type=task_type,
                        prompt_tokens=0,
                        completion_tokens=metrics.get("estimated_tokens", 0),
                        estimated=True,
                    )
                if candidate.provider_id != primary_id:
                    self._record_fallback(candidate.provider_id, "success_after_fallback")
                    self._fallback_history.append(
                        {
                            "primary": primary_id,
                            "used": candidate.provider_id,
                            "model": candidate.model,
                            "attempt": index + 1,
                            "streaming": True,
                            "elapsed": time.monotonic() - start_time,
                            "category": "success_after_fallback",
                        }
                    )
                elapsed_total = time.monotonic() - start_time
                logger.info(
                    "Stream success: provider=%s model=%s attempt=%d/%d elapsed=%s",
                    candidate.provider_id,
                    candidate.model,
                    index + 1,
                    len(candidates),
                    format_elapsed(elapsed_total),
                )
                return
            except Exception as error:
                classification = (
                    classify_provider_error(error, candidate.provider_id)
                    if not emitted_content
                    else {"category": "stream_interrupted", "message": str(error)}
                )
                last_classification = classification
                last_error = f"[{classification['category']}] {classification['message']}"
                self._circuit_breaker.record_failure(candidate.provider_id)
                self._fallback_history.append(
                    {
                        "primary": primary_id,
                        "used": candidate.provider_id,
                        "attempt": index + 1,
                        "streaming": True,
                        "category": classification.get("category", "unknown"),
                        "message": classification.get("message", ""),
                        "elapsed": time.monotonic() - start_time,
                    }
                )
                logger.warning(
                    "Stream provider %s failed (attempt %d/%d, budget=%.0fs): [%s] %s",
                    candidate.provider_id,
                    index + 1,
                    len(candidates),
                    remaining,
                    classification["category"],
                    classification["message"],
                )
                if emitted_content:
                    yield {
                        "type": "error",
                        "category": "stream_interrupted",
                        "message": f"Provider {candidate.provider_id} interrupted the response",
                    }
                    return

        yield {
            "type": "error",
            "category": last_classification.get("category", "all_failed") if last_classification else "all_failed",
            "message": f"All providers failed. Last: {last_error}",
            "detail": last_classification,
        }

    def _call_provider_stream(
        self,
        decision: RouterDecision,
        provider: ProviderSpec,
        messages: List[Dict[str, str]],
        model_override: Optional[str] = None,
        timeout_budget: Optional[float] = None,
    ) -> Iterator[Dict[str, Any]]:
        from openai import OpenAI

        model = model_override or decision.model
        base_url = provider.config.get("base_url") or PROVIDER_URLS.get(provider.id, "")
        api_key = self._key_map.get(provider.id, "")
        if provider.id in ("ollama", "sentinel_local"):
            api_key = provider.id

        provider_messages = messages
        if provider.id == "sentinel_local":
            provider_messages = [dict(message) for message in messages]
            for message in provider_messages:
                if message.get("role") == "system":
                    message["content"] = (
                        str(message.get("content", "")) + "\nUse only the supplied Sentinel context for device facts. "
                        "Do not expose chain-of-thought. /no_think"
                    )
                    break

        connect_to = CONNECT_TIMEOUT
        first_token_to = FIRST_TOKEN_TIMEOUT_LOCAL if provider.is_local else FIRST_TOKEN_TIMEOUT_NONLOCAL
        stream_idle_to = STREAM_IDLE_TIMEOUT
        if timeout_budget is not None:
            budget = max(connect_to + first_token_to + 5.0, timeout_budget)
            connect_to = min(connect_to, budget * 0.2)
            first_token_to = min(first_token_to, budget * 0.5)
            stream_idle_to = min(stream_idle_to, budget * 0.3)

        import httpx

        client = OpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=httpx.Timeout(connect=connect_to, read=first_token_to, write=connect_to, pool=connect_to),
            max_retries=0,
        )

        request_options: Dict[str, Any] = {}
        if provider.id == "nvidia":
            deep_reasoning = decision.task_type in (TaskType.REASONING, TaskType.CODE)
            request_options = {
                "temperature": 1.0,
                "top_p": 0.95,
                "max_tokens": 4096 if deep_reasoning else 1024,
                "extra_body": {
                    "chat_template_kwargs": {"enable_thinking": deep_reasoning},
                    **({"reasoning_budget": 2048} if deep_reasoning else {}),
                },
            }

        stream_start = time.monotonic()
        stream = client.chat.completions.create(
            model=model,
            messages=provider_messages,
            max_tokens=768 if provider.id == "sentinel_local" else request_options.pop("max_tokens", None),
            stream=True,
            **request_options,
        )

        first_token_ttft = None
        total_tokens = 0
        last_chunk_time = time.monotonic()
        yield {"type": "meta", "provider": decision.provider_id, "model": model}
        for chunk in stream:
            if not chunk.choices:
                continue
            now = time.monotonic()
            if first_token_ttft is None:
                first_token_ttft = now - stream_start
                yield {"type": "ttft", "seconds": first_token_ttft, "provider": decision.provider_id}
            text = chunk.choices[0].delta.content
            if text:
                total_tokens += 1
                last_chunk_time = now
                yield {"type": "delta", "text": text}
            if hasattr(chunk.usage, "completion_tokens") and chunk.usage.completion_tokens:
                total_tokens = chunk.usage.completion_tokens
            # Check stream idle timeout
            if now - last_chunk_time > stream_idle_to:
                yield {
                    "type": "error",
                    "category": "stream_idle_timeout",
                    "message": f"No data for {stream_idle_to:.0f}s",
                    "provider": decision.provider_id,
                }
                for _ in stream:
                    pass  # drain
                return

        elapsed_total = time.monotonic() - stream_start
        yield {
            "type": "metrics",
            "provider": decision.provider_id,
            "model": model,
            "ttft_seconds": first_token_ttft,
            "total_seconds": elapsed_total,
            "estimated_tokens": total_tokens,
        }
        yield {"type": "done"}

    def _call_provider(
        self,
        decision: RouterDecision,
        provider: ProviderSpec,
        messages: List[Dict[str, str]],
        model_override: Optional[str] = None,
        timeout: Optional[float] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        from openai import OpenAI

        model = model_override or decision.model
        base_url = provider.config.get("base_url") or PROVIDER_URLS.get(provider.id, "")
        api_key = self._key_map.get(provider.id, "")
        if provider.id in ("ollama", "sentinel_local"):
            api_key = provider.id

        provider_messages = messages
        if provider.id == "sentinel_local":
            provider_messages = [dict(message) for message in messages]
            for message in provider_messages:
                if message.get("role") == "system":
                    message["content"] = (
                        str(message.get("content", "")) + "\nUse only the supplied Sentinel context for device facts. "
                        "Do not expose chain-of-thought. /no_think"
                    )
                    break

        effective_timeout = timeout or (LOCAL_CALL_TIMEOUT if provider.is_local else CALL_TIMEOUT)
        client = OpenAI(base_url=base_url, api_key=api_key, timeout=effective_timeout, max_retries=0)
        request_options: Dict[str, Any] = {}
        if provider.id == "nvidia":
            deep_reasoning = decision.task_type in (TaskType.REASONING, TaskType.CODE)
            request_options = {
                "temperature": 1.0,
                "top_p": 0.95,
                "max_tokens": 4096 if deep_reasoning else 1024,
                "extra_body": {
                    "chat_template_kwargs": {"enable_thinking": deep_reasoning},
                    **({"reasoning_budget": 2048} if deep_reasoning else {}),
                },
            }

        if tools:
            request_options["tools"] = tools
            request_options["tool_choice"] = "auto"

        call_start = time.monotonic()
        resp = client.chat.completions.create(
            model=model,
            messages=provider_messages,
            max_tokens=768 if provider.id == "sentinel_local" else request_options.pop("max_tokens", None),
            **request_options,
        )
        elapsed = time.monotonic() - call_start

        usage_data = None
        if resp.usage:
            usage_data = {
                "prompt_tokens": getattr(resp.usage, "prompt_tokens", 0) or 0,
                "completion_tokens": getattr(resp.usage, "completion_tokens", 0) or 0,
                "total_tokens": getattr(resp.usage, "total_tokens", 0) or 0,
            }

        response_message = resp.choices[0].message
        tool_calls = parse_tool_call(response_message) if hasattr(response_message, "tool_calls") else []

        return {
            "response": response_message.content,
            "provider": decision.provider_id,
            "model": model,
            "usage": usage_data,
            "elapsed_seconds": elapsed,
            "tool_calls": tool_calls,
        }

    def chat_with_provider(
        self,
        messages: List[Dict[str, str]],
        provider_id: str,
        model: str,
        task_type: TaskType = TaskType.QUICK,
    ) -> Dict[str, Any]:
        provider = self._providers.get(provider_id)
        if not provider:
            raise ValueError(f"Unknown provider '{provider_id}'")
        if provider.requires_key and not self.has_api_key(provider_id):
            raise ValueError(
                f"Provider '{provider_id}' requires an API key but none is configured. "
                "Set the API key via the AI Config panel or the api_key parameter."
            )
        availability = self.provider_availability(provider_id)
        if not availability.available:
            raise RuntimeError(f"Provider '{provider_id}' is unavailable: {availability.reason}")
        decision = RouterDecision(
            provider_id=provider_id,
            model=model or provider.default_model,
            task_type=task_type,
            strategy="manual",
            reason=f"Direct call to {provider_id}/{model or provider.default_model}",
        )
        return self._call_provider(decision, provider, messages)

    def check_health(self, provider_id: str, timeout: float = 5.0) -> Dict[str, Any]:
        provider = self._providers.get(provider_id)
        if not provider:
            return {"available": False, "error": f"Unknown provider '{provider_id}'"}
        base_url = provider.config.get("base_url") or PROVIDER_URLS.get(provider_id, "")
        if not base_url:
            return {"available": False, "error": "no_base_url", "provider": provider_id}
        try:
            import httpx

            api_key = self._key_map.get(provider_id, "")
            headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
            r = httpx.get(f"{base_url}/models", headers=headers, timeout=timeout)
            if r.status_code == 401:
                return {"available": False, "error": "invalid_api_key", "status_code": 401, "provider": provider_id}
            if r.status_code == 403:
                return {"available": False, "error": "key_lacks_access", "status_code": 403, "provider": provider_id}
            if r.status_code == 429:
                return {"available": False, "error": "rate_limited", "status_code": 429, "provider": provider_id}
            if r.status_code >= 500:
                return {
                    "available": False,
                    "error": f"provider_error_{r.status_code}",
                    "status_code": r.status_code,
                    "provider": provider_id,
                }
            return {"available": r.is_success, "status_code": r.status_code, "provider": provider_id}
        except (httpx.ConnectError, httpx.ConnectTimeout):
            return {"available": False, "error": "connection_failed", "provider": provider_id}
        except (httpx.ReadTimeout, httpx.PoolTimeout, httpx.WriteTimeout):
            return {"available": False, "error": "timeout", "provider": provider_id}
        except httpx.HTTPError as e:
            return {"available": False, "error": str(e), "provider": provider_id}
        except Exception as e:
            return {"available": False, "error": str(e), "provider": provider_id}

    def chat_with_decision(
        self,
        messages: List[Dict[str, str]],
        decision: Any,
        task_type: TaskType = TaskType.QUICK,
    ) -> Dict[str, Any]:
        from .intelligence_orchestrator import IntelligenceDecision
        if not isinstance(decision, IntelligenceDecision):
            raise ValueError("Expected IntelligenceDecision object")
        if decision.status == "no_capable_model":
            raise RuntimeError(
                f"No available model supports required capabilities: {decision.required_capabilities}"
            )
        if decision.status == "no_registry":
            raise RuntimeError("No ModelRegistry configured in IntelligenceOrchestrator")
        return self.chat_with_provider(
            messages=messages,
            provider_id=decision.provider,
            model=decision.model_id,
            task_type=task_type,
        )

    def chat_with_conversation(
        self,
        user_message: str,
        conversation_context: Any,
        decision: Any,
        task_type: TaskType = TaskType.QUICK,
    ) -> Dict[str, Any]:
        from .conversation_manager import ConversationManager, ConversationContext, ContextPackage
        conv_manager = getattr(self, "_conversation_manager", None)
        if conv_manager is None:
            conv_manager = ConversationManager()
        conv_ctx = conversation_context
        if isinstance(conv_ctx, ConversationContext):
            pkg = conv_manager.prepare_for_model(
                context=conv_ctx,
                model_id=decision.model_id,
                user_message=user_message,
            )
        else:
            pkg = None

        if pkg is not None:
            messages = pkg.to_messages(user_message=user_message)
        else:
            messages = [
                {"role": "system", "content": "You are Sentinel."},
                {"role": "user", "content": user_message},
            ]

        result = self.chat_with_provider(
            messages=messages,
            provider_id=decision.provider,
            model=decision.model_id,
            task_type=task_type,
        )
        if pkg is not None and conv_manager:
            response_text = result.get("response", "")
            conv_manager.update_after_turn(
                conv_ctx, user_message=user_message, assistant_response=response_text,
                model_id=decision.model_id,
            )
            result["context_package"] = pkg.to_dict()
        return result

    @property
    def circuit_breaker(self) -> CircuitBreaker:
        return self._circuit_breaker

    def list_providers(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": p.id,
                "name": p.name,
                "task_types": [t.value for t in p.task_types],
                "requires_key": p.requires_key,
                "is_local": p.is_local,
                "has_key": self.has_api_key(p.id),
                "default_model": p.default_model,
                "availability": self.provider_availability(p.id).to_dict(),
                "circuit_state": self._circuit_breaker.get_state(p.id) if self._circuit_breaker else "unknown",
                "fallback_chain": list(p.fallback_chain),
            }
            for p in self._providers.values()
        ]

    def get_routing_config(self) -> Dict[str, Any]:
        return {
            "preferred_provider": self._preferred_provider,
            "strategy": self._strategy,
            "task_type_map": {k.value: v for k, v in self._task_type_map.items()},
            "max_fallbacks": self._max_fallbacks,
            "fallback_strategy": self._fallback_strategy,
            "offline_mode": self._offline_mode,
        }
