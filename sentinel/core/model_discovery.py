from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, Set
import logging

logger = logging.getLogger(__name__)

MODEL_CAPABILITY_HINTS: Dict[str, Dict[str, Any]] = {
    "qwen": {"supports_coding": True, "supports_reasoning": True},
    "qwen2": {"supports_coding": True, "supports_reasoning": True},
    "qwen2.5": {"supports_coding": True, "supports_reasoning": True},
    "qwen3": {"supports_coding": True, "supports_reasoning": True},
    "deepseek": {"supports_coding": True, "supports_reasoning": True},
    "codestral": {"supports_coding": True, "supports_reasoning": False},
    "mistral": {"supports_coding": True, "supports_reasoning": True},
    "llama": {"supports_coding": True, "supports_reasoning": True},
    "llama2": {"supports_coding": True, "supports_reasoning": True},
    "llama3": {"supports_coding": True, "supports_reasoning": True},
    "nemotron": {"supports_coding": True, "supports_reasoning": True},
    "phi": {"supports_coding": True, "supports_reasoning": False},
    "phi3": {"supports_coding": True, "supports_reasoning": True},
    "gemma": {"supports_coding": True, "supports_reasoning": True},
    "gemma2": {"supports_coding": True, "supports_reasoning": True},
    "gpt-3.5": {"supports_coding": True, "supports_reasoning": False},
    "gpt-4": {"supports_coding": True, "supports_reasoning": True},
    "gpt-4o": {"supports_coding": True, "supports_reasoning": True},
    "gpt-4o-mini": {"supports_coding": True, "supports_reasoning": True},
    "claude": {"supports_coding": True, "supports_reasoning": True},
    "claude-3": {"supports_coding": True, "supports_reasoning": True},
    "gemini": {"supports_coding": True, "supports_reasoning": True},
    "gemini-2.0": {"supports_coding": True, "supports_reasoning": True},
    "gemini-2.5": {"supports_coding": True, "supports_reasoning": True},
    "starcoder": {"supports_coding": True, "supports_reasoning": False},
    "codeqwen": {"supports_coding": True, "supports_reasoning": False},
    "nomic-embed": {"supports_embeddings": True},
    "bge": {"supports_embeddings": True},
    "mxbai": {"supports_embeddings": True},
}

CONTEXT_WINDOW_HINTS: Dict[str, int] = {
    "qwen3:8b": 32768,
    "qwen3:14b": 32768,
    "qwen3:32b": 32768,
    "qwen3:70b": 32768,
    "qwen2.5:7b": 32768,
    "qwen2.5:14b": 32768,
    "qwen2.5:32b": 32768,
    "qwen2.5:72b": 32768,
    "deepseek-v3": 65536,
    "deepseek-r1": 65536,
    "llama3:8b": 8192,
    "llama3:70b": 8192,
    "llama3.1:8b": 131072,
    "llama3.1:70b": 131072,
    "llama3.2:3b": 131072,
    "llama3.3": 131072,
    "nemotron": 128000,
    "phi3": 128000,
    "gemma2:9b": 8192,
    "gemma2:27b": 8192,
    "mistral": 32768,
    "codestral": 32768,
}

SPEED_HINTS: Dict[str, str] = {
    "7b": "fast",
    "8b": "fast",
    "14b": "medium",
    "32b": "medium",
    "70b": "slow",
    "72b": "slow",
}

OLLAMA_DEFAULT_URL = "http://localhost:11434"
LMSTUDIO_DEFAULT_URL = "http://localhost:1234"


@dataclass
class DiscoveredModel:
    model_id: str = ""
    provider: str = ""
    local: bool = False
    context_window: int = 4096
    supports_coding: bool = False
    supports_reasoning: bool = False
    supports_tool_calling: bool = False
    supports_vision: bool = False
    supports_embeddings: bool = False
    speed: str = "unknown"
    cost: float = 0.0
    tags: List[str] = field(default_factory=list)
    status: str = "available"

    def to_metadata(self) -> Any:
        from sentinel.models import ModelMetadata, ModelStatus
        status_map = {
            "available": ModelStatus.AVAILABLE,
            "unavailable": ModelStatus.UNAVAILABLE,
            "experimental": ModelStatus.EXPERIMENTAL,
            "deprecated": ModelStatus.DEPRECATED,
        }
        return ModelMetadata(
            id=self.model_id,
            provider=self.provider,
            context_window=self.context_window,
            supports_tool_calling=self.supports_tool_calling,
            supports_vision=self.supports_vision,
            supports_coding=self.supports_coding,
            supports_reasoning=self.supports_reasoning,
            supports_embeddings=self.supports_embeddings,
            speed=self.speed,
            cost=self.cost,
            local=self.local,
            status=status_map.get(self.status, ModelStatus.AVAILABLE),
            tags=self.tags,
        )


class ModelProviderDiscovery(Protocol):
    def discover_models(self) -> List[DiscoveredModel]: ...

    async def discover_models_async(self) -> List[DiscoveredModel]: ...

    async def health_check_async(self) -> bool: ...


class OllamaDiscovery:
    def __init__(self, base_url: str = OLLAMA_DEFAULT_URL):
        self._base_url = base_url.rstrip("/")

    async def health_check_async(self) -> bool:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self._base_url}/api/tags")
                return resp.status_code == 200
        except Exception:
            return False

    async def discover_models_async(self) -> List[DiscoveredModel]:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self._base_url}/api/tags")
            if resp.status_code != 200:
                logger.warning("Ollama API returned status %d", resp.status_code)
                return []
            data = resp.json()
            models = data.get("models", [])
            result = []
            for m in models:
                name = m.get("name", "")
                if not name:
                    continue
                result.append(self._build_discovered(name))
            logger.info("Ollama async discovery: found %d models", len(result))
            return result
        except ImportError:
            logger.warning("httpx not available, cannot discover Ollama models")
            return []
        except Exception as e:
            logger.warning("Ollama async discovery failed: %s", e)
            return []

    def discover_models(self) -> List[DiscoveredModel]:
        try:
            import httpx
            resp = httpx.get(f"{self._base_url}/api/tags", timeout=5.0)
            if resp.status_code != 200:
                logger.warning("Ollama API returned status %d", resp.status_code)
                return []
            data = resp.json()
            models = data.get("models", [])
            result = []
            for m in models:
                name = m.get("name", "")
                if not name:
                    continue
                model_id = name
                dm = self._build_discovered(model_id)
                result.append(dm)
            logger.info("Ollama discovery: found %d models", len(result))
            return result
        except ImportError:
            logger.warning("httpx not available, cannot discover Ollama models")
            return []
        except Exception as e:
            logger.warning("Ollama discovery failed: %s", e)
            return []

    def _build_discovered(self, model_id: str) -> DiscoveredModel:
        hints = self._get_hints(model_id)
        speed = self._infer_speed(model_id)
        ctx = self._infer_context_window(model_id)
        return DiscoveredModel(
            model_id=model_id,
            provider="ollama",
            local=True,
            context_window=ctx,
            supports_coding=hints.get("supports_coding", False),
            supports_reasoning=hints.get("supports_reasoning", False),
            supports_tool_calling=hints.get("supports_tool_calling", False),
            supports_vision=hints.get("supports_vision", False),
            supports_embeddings=hints.get("supports_embeddings", False),
            speed=speed,
            cost=0.0,
            tags=["local", "ollama"],
            status="available",
        )

    def _get_hints(self, model_id: str) -> Dict[str, Any]:
        model_lower = model_id.lower().replace(":", "/").split("/")[0]
        for key in sorted(MODEL_CAPABILITY_HINTS.keys(), key=len, reverse=True):
            if key in model_lower:
                return MODEL_CAPABILITY_HINTS[key]
        return {}

    def _infer_speed(self, model_id: str) -> str:
        model_lower = model_id.lower()
        for size_tag, speed in sorted(SPEED_HINTS.items(), key=len, reverse=True):
            if size_tag in model_lower:
                return speed
        return "unknown"

    def _infer_context_window(self, model_id: str) -> int:
        model_lower = model_id.lower().replace("_", ":").replace("-", ":")
        for key in sorted(CONTEXT_WINDOW_HINTS.keys(), key=len, reverse=True):
            if key in model_lower:
                return CONTEXT_WINDOW_HINTS[key]
        return 4096


class LMStudioDiscovery:
    def __init__(self, base_url: str = LMSTUDIO_DEFAULT_URL):
        self._base_url = base_url.rstrip("/")

    async def health_check_async(self) -> bool:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self._base_url}/v1/models")
                return resp.status_code == 200
        except Exception:
            return False

    async def discover_models_async(self) -> List[DiscoveredModel]:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self._base_url}/v1/models")
            if resp.status_code != 200:
                logger.warning("LM Studio API returned status %d", resp.status_code)
                return []
            data = resp.json()
            models_data = data if isinstance(data, list) else data.get("data", [])
            result = []
            for m in models_data:
                model_id = ""
                if isinstance(m, dict):
                    model_id = m.get("id", m.get("model", ""))
                elif isinstance(m, str):
                    model_id = m
                if not model_id:
                    continue
                result.append(self._build_discovered(model_id))
            logger.info("LM Studio async discovery: found %d models", len(result))
            return result
        except ImportError:
            logger.warning("httpx not available, cannot discover LM Studio models")
            return []
        except Exception as e:
            logger.warning("LM Studio async discovery failed: %s", e)
            return []

    def discover_models(self) -> List[DiscoveredModel]:
        try:
            import httpx
            resp = httpx.get(f"{self._base_url}/v1/models", timeout=5.0)
            if resp.status_code != 200:
                logger.warning("LM Studio API returned status %d", resp.status_code)
                return []
            data = resp.json()
            models_data = data if isinstance(data, list) else data.get("data", [])
            result = []
            for m in models_data:
                model_id = ""
                if isinstance(m, dict):
                    model_id = m.get("id", m.get("model", ""))
                elif isinstance(m, str):
                    model_id = m
                if not model_id:
                    continue
                dm = self._build_discovered(model_id)
                result.append(dm)
            logger.info("LM Studio discovery: found %d models", len(result))
            return result
        except ImportError:
            logger.warning("httpx not available, cannot discover LM Studio models")
            return []
        except Exception as e:
            logger.warning("LM Studio discovery failed: %s", e)
            return []

    def _build_discovered(self, model_id: str) -> DiscoveredModel:
        hints = self._get_hints(model_id)
        speed = self._infer_speed(model_id)
        ctx = self._infer_context_window(model_id)
        return DiscoveredModel(
            model_id=model_id,
            provider="lmstudio",
            local=True,
            context_window=ctx,
            supports_coding=hints.get("supports_coding", False),
            supports_reasoning=hints.get("supports_reasoning", False),
            supports_tool_calling=hints.get("supports_tool_calling", False),
            supports_vision=hints.get("supports_vision", False),
            supports_embeddings=hints.get("supports_embeddings", False),
            speed=speed,
            cost=0.0,
            tags=["local", "lmstudio"],
            status="available",
        )

    def _get_hints(self, model_id: str) -> Dict[str, Any]:
        model_lower = model_id.lower()
        for key in sorted(MODEL_CAPABILITY_HINTS.keys(), key=len, reverse=True):
            if key in model_lower:
                return MODEL_CAPABILITY_HINTS[key]
        return {}

    def _infer_speed(self, model_id: str) -> str:
        model_lower = model_id.lower()
        for size_tag, speed in sorted(SPEED_HINTS.items(), key=len, reverse=True):
            if size_tag in model_lower:
                return speed
        return "unknown"

    def _infer_context_window(self, model_id: str) -> int:
        model_lower = model_id.lower().replace("_", ":").replace("-", ":")
        for key in sorted(CONTEXT_WINDOW_HINTS.keys(), key=len, reverse=True):
            if key in model_lower:
                return CONTEXT_WINDOW_HINTS[key]
        return 4096


class CloudProviderDiscovery:
    def __init__(self, provider_id: str, base_url: str, api_key: str = "", default_model: str = ""):
        self._provider_id = provider_id
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._default_model = default_model

    async def health_check_async(self) -> bool:
        if not self._api_key:
            return False
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{self._base_url}/models",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
                return resp.status_code == 200
        except Exception:
            return False

    async def discover_models_async(self) -> List[DiscoveredModel]:
        if not self._api_key:
            logger.info("Cloud provider '%s': no API key, skipping discovery", self._provider_id)
            return []
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{self._base_url}/models",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
            if resp.status_code != 200:
                logger.warning("Provider '%s' API returned status %d", self._provider_id, resp.status_code)
                return []
            data = resp.json()
            models_data = data.get("data", [])
            result = []
            for m in models_data:
                model_id = m.get("id", "") if isinstance(m, dict) else (m if isinstance(m, str) else "")
                if not model_id:
                    continue
                result.append(self._build_discovered(model_id))
            logger.info("Provider '%s' async discovery: found %d models", self._provider_id, len(result))
            return result
        except ImportError:
            logger.debug("httpx not available, cannot discover %s models", self._provider_id)
            return []
        except Exception as e:
            logger.warning("Provider '%s' async discovery failed: %s", self._provider_id, e)
            return []

    def discover_models(self) -> List[DiscoveredModel]:
        if not self._api_key:
            logger.info("Cloud provider '%s': no API key, skipping discovery", self._provider_id)
            return []
        try:
            import httpx
            resp = httpx.get(
                f"{self._base_url}/models",
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=10.0,
            )
            if resp.status_code != 200:
                logger.warning("Provider '%s' API returned status %d", self._provider_id, resp.status_code)
                return []
            data = resp.json()
            models_data = data.get("data", [])
            result = []
            for m in models_data:
                model_id = m.get("id", "") if isinstance(m, dict) else (m if isinstance(m, str) else "")
                if not model_id:
                    continue
                dm = self._build_discovered(model_id)
                result.append(dm)
            logger.info("Provider '%s' discovery: found %d models", self._provider_id, len(result))
            return result
        except ImportError:
            logger.debug("httpx not available, cannot discover %s models", self._provider_id)
            return []
        except Exception as e:
            logger.warning("Provider '%s' discovery failed: %s", self._provider_id, e)
            return []

    def _build_discovered(self, model_id: str) -> DiscoveredModel:
        hints = self._get_hints(model_id)
        speed = self._infer_speed(model_id)
        ctx = self._infer_context_window(model_id)
        tags = [self._provider_id]
        return DiscoveredModel(
            model_id=model_id,
            provider=self._provider_id,
            local=False,
            context_window=ctx,
            supports_coding=hints.get("supports_coding", False),
            supports_reasoning=hints.get("supports_reasoning", False),
            supports_tool_calling=hints.get("supports_tool_calling", False),
            supports_vision=hints.get("supports_vision", False),
            supports_embeddings=hints.get("supports_embeddings", False),
            speed=speed,
            cost=0.0,
            tags=tags,
            status="available",
        )

    def _get_hints(self, model_id: str) -> Dict[str, Any]:
        model_lower = model_id.lower()
        for key in sorted(MODEL_CAPABILITY_HINTS.keys(), key=len, reverse=True):
            if key in model_lower:
                return MODEL_CAPABILITY_HINTS[key]
        return {}

    def _infer_speed(self, model_id: str) -> str:
        return "fast"

    def _infer_context_window(self, model_id: str) -> int:
        model_lower = model_id.lower().replace("_", ":").replace("-", ":")
        for key in sorted(CONTEXT_WINDOW_HINTS.keys(), key=len, reverse=True):
            if key in model_lower:
                return CONTEXT_WINDOW_HINTS[key]
        return 128000


CLOUD_PROVIDER_CONFIGS: List[Dict[str, str]] = [
    {"id": "openai", "base_url": "https://api.openai.com/v1", "env_key": "SENTINEL_API_KEY_OPENAI"},
    {"id": "anthropic", "base_url": "https://api.anthropic.com/v1", "env_key": "SENTINEL_API_KEY_ANTHROPIC"},
    {"id": "gemini", "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/", "env_key": "SENTINEL_API_KEY_GEMINI"},
    {"id": "deepseek", "base_url": "https://api.deepseek.com/v1", "env_key": "SENTINEL_API_KEY_DEEPSEEK"},
    {"id": "groq", "base_url": "https://api.groq.com/openai/v1", "env_key": "SENTINEL_API_KEY_GROQ"},
    {"id": "github_models", "base_url": "https://models.inference.ai.azure.com", "env_key": "SENTINEL_API_KEY_GITHUB"},
    {"id": "cerebras", "base_url": "https://api.cerebras.ai/v1", "env_key": "SENTINEL_API_KEY_CEREBRAS"},
    {"id": "mistral", "base_url": "https://api.mistral.ai/v1", "env_key": "SENTINEL_API_KEY_MISTRAL"},
    {"id": "openrouter", "base_url": "https://openrouter.ai/api/v1", "env_key": "SENTINEL_API_KEY_OPENROUTER"},
]


class ModelDiscovery:
    def __init__(
        self,
        model_registry: Any = None,
        discoverers: Optional[List[Any]] = None,
        vault: Any = None,
    ):
        self._model_registry = model_registry
        self._discoverers: List[Any] = discoverers or []
        self._vault = vault
        self._all_discovered: Dict[str, List[DiscoveredModel]] = {}
        self._has_run = False
        self._defaults_added = False
        self._model_repository = None

    def set_model_registry(self, registry: Any) -> None:
        self._model_registry = registry

    def set_model_repository(self, repo: Any) -> None:
        self._model_repository = repo

    def set_vault(self, vault: Any) -> None:
        self._vault = vault

    def add_discoverer(self, discoverer: Any) -> None:
        self._discoverers.append(discoverer)

    def add_default_discoverers(self) -> None:
        if getattr(self, "_defaults_added", False):
            return
        self._discoverers.append(OllamaDiscovery())
        self._discoverers.append(LMStudioDiscovery())
        for cfg in CLOUD_PROVIDER_CONFIGS:
            api_key = self._resolve_api_key(cfg["id"], cfg.get("env_key", ""))
            if api_key:
                self._discoverers.append(CloudProviderDiscovery(
                    provider_id=cfg["id"],
                    base_url=cfg["base_url"],
                    api_key=api_key,
                ))
        self._defaults_added = True

    def discover_all(self) -> Dict[str, List[DiscoveredModel]]:
        results: Dict[str, List[DiscoveredModel]] = {}
        for discoverer in self._discoverers:
            try:
                provider = getattr(discoverer, "_provider_id", None) or type(discoverer).__name__.replace("Discovery", "").lower()
                models = discoverer.discover_models()
                results[provider] = models
            except Exception as e:
                logger.warning("Discovery error for %s: %s", type(discoverer).__name__, e)
                results[type(discoverer).__name__] = []
        self._all_discovered = results
        self._has_run = True
        total = sum(len(v) for v in results.values())
        logger.info("Model discovery complete: %d models from %d providers", total, len(results))
        return results

    async def discover_all_async(self) -> Dict[str, List[DiscoveredModel]]:
        results: Dict[str, List[DiscoveredModel]] = {}
        for discoverer in self._discoverers:
            try:
                provider = getattr(discoverer, "_provider_id", None) or type(discoverer).__name__.replace("Discovery", "").lower()
                if hasattr(discoverer, "discover_models_async"):
                    models = await discoverer.discover_models_async()
                else:
                    models = discoverer.discover_models()
                results[provider] = models
            except Exception as e:
                logger.warning("Async discovery error for %s: %s", type(discoverer).__name__, e)
                results[type(discoverer).__name__] = []
        self._all_discovered = results
        self._has_run = True
        total = sum(len(v) for v in results.values())
        logger.info("Model discovery (async) complete: %d models from %d providers", total, len(results))
        return results

    def sync_registry(self) -> Dict[str, Any]:
        if not self._has_run:
            self.discover_all()
        if self._model_registry is None:
            logger.warning("No ModelRegistry configured, cannot sync")
            return {"status": "no_registry", "added": 0, "updated": 0, "removed": 0}

        discovered_ids: Set[str] = set()
        added = 0
        updated = 0
        removed = 0

        for provider, models in self._all_discovered.items():
            for dm in models:
                discovered_ids.add(dm.model_id)
                metadata = dm.to_metadata()
                existing = self._model_registry.get(dm.model_id)
                if existing is None:
                    try:
                        self._model_registry.register(metadata)
                        added += 1
                        logger.info("New model discovered: %s (%s)", dm.model_id, provider)
                    except ValueError:
                        updated += 1
                else:
                    updated += 1

        registry_ids = {m.id for m in self._model_registry.list_all()}
        missing = registry_ids - discovered_ids
        for mid in missing:
            model = self._model_registry.get(mid)
            if model and model.local:
                logger.info("Local model no longer available: %s", mid)
                removed += 1

        logger.info("Registry sync: %d added, %d updated, %d removed", added, updated, removed)
        return {
            "status": "success",
            "added": added,
            "updated": updated,
            "removed": removed,
            "total_after": self._model_registry.count(),
        }

    async def sync_registry_async(self) -> Dict[str, Any]:
        if not self._has_run:
            await self.discover_all_async()
        if self._model_registry is None:
            logger.warning("No ModelRegistry configured, cannot sync")
            return {"status": "no_registry", "added": 0, "updated": 0, "removed": 0}

        discovered_ids: Set[str] = set()
        added = 0
        updated = 0
        removed = 0

        for provider, models in self._all_discovered.items():
            for dm in models:
                discovered_ids.add(dm.model_id)
                metadata = dm.to_metadata()
                existing = self._model_registry.get(dm.model_id)
                if existing is None:
                    try:
                        if hasattr(self._model_registry, "upsert"):
                            self._model_registry.upsert(metadata)
                            added += 1
                        else:
                            self._model_registry.register(metadata)
                            added += 1
                        logger.info("New model discovered (async): %s (%s)", dm.model_id, provider)
                    except ValueError:
                        updated += 1
                else:
                    updated += 1

        if self._model_repository is not None:
            try:
                for provider, models in self._all_discovered.items():
                    for dm in models:
                        await self._model_repository.save(self._model_registry.to_stored_model(dm.to_metadata()))
                logger.info("Registry sync: %d models persisted to repository", sum(len(v) for v in self._all_discovered.values()))
            except Exception as e:
                logger.warning("Registry sync persistence failed: %s", e)

        return {
            "status": "success",
            "added": added,
            "updated": updated,
            "removed": removed,
            "total_after": self._model_registry.count(),
        }

    def run_full_discovery(self) -> Dict[str, Any]:
        self.discover_all()
        return self.sync_registry()

    async def run_full_discovery_async(self) -> Dict[str, Any]:
        await self.discover_all_async()
        return await self.sync_registry_async()

    async def health_check_all(self) -> Dict[str, bool]:
        """Comprueba la salud de todos los discoverers configurados."""
        results: Dict[str, bool] = {}
        for discoverer in self._discoverers:
            try:
                provider = getattr(discoverer, "_provider_id", None) or type(discoverer).__name__.replace("Discovery", "").lower()
                if hasattr(discoverer, "health_check_async"):
                    results[provider] = await discoverer.health_check_async()
                else:
                    results[provider] = bool(discoverer.discover_models())
            except Exception as e:
                logger.warning("Health check error for %s: %s", type(discoverer).__name__, e)
                results[type(discoverer).__name__] = False
        return results

    def get_capabilities(self, model_id: str) -> Dict[str, Any]:
        """Capacidades declaradas para un modelo conocido."""
        if self._model_registry is not None:
            model = self._model_registry.get(model_id)
            if model is not None:
                return {
                    "model_id": model.id,
                    "provider": model.provider,
                    "context": model.context_window,
                    "capabilities": [
                        cap for cap, supported in {
                            "coding": model.supports_coding,
                            "reasoning": model.supports_reasoning,
                            "tool_calling": model.supports_tool_calling,
                            "vision": model.supports_vision,
                            "embeddings": model.supports_embeddings,
                        }.items() if supported
                    ],
                    "local": model.local,
                    "speed": model.speed,
                }
        hints = self._resolve_hints(model_id)
        caps = [c for c, v in {
            "coding": hints.get("supports_coding", False),
            "reasoning": hints.get("supports_reasoning", False),
            "tool_calling": hints.get("supports_tool_calling", False),
            "vision": hints.get("supports_vision", False),
        }.items() if v]
        if hints.get("supports_embeddings"):
            caps.append("embeddings")
        return {
            "model_id": model_id,
            "provider": "",
            "context": self._infer_context_window(model_id),
            "capabilities": caps,
            "local": False,
        }

    def _resolve_hints(self, model_id: str) -> Dict[str, Any]:
        model_lower = model_id.lower()
        for key in sorted(MODEL_CAPABILITY_HINTS.keys(), key=len, reverse=True):
            if key in model_lower:
                return MODEL_CAPABILITY_HINTS[key]
        return {}

    @staticmethod
    def _infer_context_window(model_id: str) -> int:
        model_lower = model_id.lower().replace("_", ":").replace("-", ":")
        for key in sorted(CONTEXT_WINDOW_HINTS.keys(), key=len, reverse=True):
            if key in model_lower:
                return CONTEXT_WINDOW_HINTS[key]
        return 4096

    def get_discovered_models(self) -> Dict[str, List[DiscoveredModel]]:
        return dict(self._all_discovered)

    def get_discoverers(self) -> List[Any]:
        return list(self._discoverers)

    def _resolve_api_key(self, provider_id: str, env_key: str) -> str:
        import os
        key = os.environ.get(env_key, "")
        if key:
            return key
        if self._vault is not None:
            try:
                stored = self._vault.reveal_value(f"ai-provider-{provider_id}")
                if stored:
                    return stored
            except Exception:
                logger.warning("Failed to reveal API key for provider '%s'", provider_id, exc_info=True)
        return ""
