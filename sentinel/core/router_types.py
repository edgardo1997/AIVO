from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


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


@dataclass
class RouterDecision:
    provider_id: str
    model: str
    task_type: TaskType
    strategy: str
    reason: str
    selection_trace: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data = {"provider_id": self.provider_id, "model": self.model, "task_type": self.task_type.value, "strategy": self.strategy, "reason": self.reason}
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
        return {"provider_id": self.provider_id, "available": self.available, "reason": self.reason, "checked_at": self.checked_at}


ROUTING_STRATEGIES = ["priority", "cost", "local_first", "smart", "manual"]
OFFLINE_MODES = ["off", "auto", "force_local"]
FALLBACK_STRATEGIES = ["chain", "round_robin", "broadcast"]

TOTAL_TIMEOUT_BUDGET = 120.0
CONNECT_TIMEOUT = 10.0
FIRST_TOKEN_TIMEOUT_NONLOCAL = 30.0
FIRST_TOKEN_TIMEOUT_LOCAL = 60.0
STREAM_IDLE_TIMEOUT = 30.0
CALL_TIMEOUT = 60.0
LOCAL_CALL_TIMEOUT = 120.0

PROVIDER_URLS: Dict[str, str] = {
    "openrouter": "https://openrouter.ai/api/v1", "deepseek": "https://api.deepseek.com/v1",
    "groq": "https://api.groq.com/openai/v1", "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "github_models": "https://models.inference.ai.azure.com", "cerebras": "https://api.cerebras.ai/v1",
    "mistral": "https://api.mistral.ai/v1", "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com/v1", "nvidia": "https://integrate.api.nvidia.com/v1",
    "nvidia-nemotron": "https://integrate.api.nvidia.com/v1", "sentinel_local": "http://127.0.0.1:11435/v1",
    "ollama": "http://localhost:11434/v1",
}

BUILTIN_PROVIDERS = [
    ProviderSpec(id="deepseek", name="DeepSeek v4 Flash (Free)", task_types=[TaskType.REASONING, TaskType.CODE, TaskType.QUICK, TaskType.ANALYSIS, TaskType.CREATIVE], requires_key=True, default_model="deepseek/deepseek-v4-flash:free", priority=10, config={"base_url": "https://api.deepseek.com/v1"}, fallback_chain=["nvidia", "sentinel_local"]),
    ProviderSpec(id="nvidia-nemotron", name="NVIDIA Nemotron (Free)", task_types=[TaskType.REASONING, TaskType.CODE, TaskType.QUICK, TaskType.ANALYSIS], requires_key=True, default_model="nvidia/nemotron-3-super-120b-a12b", priority=20, config={"base_url": "https://integrate.api.nvidia.com/v1"}, fallback_chain=["sentinel_local"]),
    ProviderSpec(id="openrouter", name="OpenRouter", task_types=[TaskType.REASONING, TaskType.ANALYSIS, TaskType.QUICK, TaskType.CODE, TaskType.CREATIVE], requires_key=True, default_model="deepseek/deepseek-v4-flash:free", priority=30),
    ProviderSpec(id="groq", name="Groq", task_types=[TaskType.QUICK, TaskType.ANALYSIS], requires_key=True, default_model="llama-3.3-70b-versatile", priority=25),
    ProviderSpec(id="gemini", name="Gemini", task_types=[TaskType.REASONING, TaskType.ANALYSIS, TaskType.CREATIVE], requires_key=True, default_model="gemini-2.5-flash", priority=18),
    ProviderSpec(id="github_models", name="GitHub Models (Free)", task_types=[TaskType.QUICK, TaskType.CODE, TaskType.REASONING, TaskType.ANALYSIS], requires_key=True, default_model="gpt-4o", priority=12, config={"base_url": "https://models.inference.ai.azure.com"}, fallback_chain=["sentinel_local"]),
    ProviderSpec(id="openai", name="OpenAI", task_types=[TaskType.REASONING, TaskType.CODE, TaskType.CREATIVE], requires_key=True, default_model="gpt-4o", priority=22),
    ProviderSpec(id="anthropic", name="Anthropic", task_types=[TaskType.REASONING, TaskType.ANALYSIS, TaskType.CODE], requires_key=True, default_model="claude-sonnet-4", priority=22),
    ProviderSpec(id="sentinel_local", name="Sentinel Local", task_types=[TaskType.LOCAL, TaskType.QUICK, TaskType.REASONING, TaskType.ANALYSIS, TaskType.CODE, TaskType.CREATIVE], requires_key=False, is_local=True, default_model="Qwen3-1.7B-Q8_0.gguf", priority=50, config={"hardware": {"working_set_gb": 3.0, "minimum_cpu_cores": 2}}),
    ProviderSpec(id="ollama", name="Ollama", task_types=[TaskType.LOCAL, TaskType.QUICK], requires_key=False, is_local=True, default_model="llama3", priority=30, config={"hardware": {"working_set_gb": 6.0, "minimum_cpu_cores": 4}}),
    ProviderSpec(id="cerebras", name="Cerebras", task_types=[TaskType.QUICK, TaskType.ANALYSIS], requires_key=True, default_model="llama-3.3-70b", priority=14),
    ProviderSpec(id="mistral", name="Mistral", task_types=[TaskType.REASONING, TaskType.CODE, TaskType.ANALYSIS], requires_key=True, default_model="mistral-large-latest", priority=16),
    ProviderSpec(id="nvidia", name="NVIDIA NIM", task_types=[TaskType.REASONING, TaskType.ANALYSIS, TaskType.QUICK, TaskType.CODE, TaskType.CREATIVE], requires_key=True, default_model="nvidia/nemotron-3-super-120b-a12b", priority=28),
]


def classify_provider_error(exception: Exception, provider_id: str) -> Dict[str, Any]:
    msg = str(exception).lower()
    if "timeout" in msg or "timed out" in msg:
        return {"category": "timeout", "message": str(exception), "provider": provider_id}
    if "rate_limit" in msg or "429" in msg:
        return {"category": "rate_limit", "message": str(exception), "provider": provider_id}
    if "unauthorized" in msg or "401" in msg or "invalid_api_key" in msg or "auth" in msg:
        return {"category": "auth", "message": str(exception), "provider": provider_id}
    if "insufficient_quota" in msg or "402" in msg or "billing" in msg:
        return {"category": "quota", "message": str(exception), "provider": provider_id}
    if "context_length" in msg or "max_tokens" in msg or "token_limit" in msg:
        return {"category": "context_overflow", "message": str(exception), "provider": provider_id}
    if "connection" in msg or "reset" in msg or "refused" in msg or "resolve" in msg:
        return {"category": "connection", "message": str(exception), "provider": provider_id}
    if "unavailable" in msg or "503" in msg or "502" in msg:
        return {"category": "service_unavailable", "message": str(exception), "provider": provider_id}
    return {"category": "unknown", "message": str(exception), "provider": provider_id}


def format_elapsed(seconds: float) -> str:
    if seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    if seconds < 60:
        return f"{seconds:.1f}s"
    m, s = divmod(int(seconds), 60)
    return f"{m}m{s}s"
