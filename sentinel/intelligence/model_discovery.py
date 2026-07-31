"""ModelDiscovery — Descubre automáticamente modelos disponibles.

Detecta:
  - Local: Ollama, LM Studio, llama.cpp servers
  - Cloud: OpenAI, Anthropic, Google (por configuración/env vars)
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ModelCapability:
    name: str
    provider: str
    local: bool = True
    context_size: int = 4096
    cost: float = 0.0
    latency_estimate: float = 1.0
    capabilities: List[str] = field(default_factory=list)
    model_family: str = ""


# Ollama models known capabilities
OLLAMA_MODEL_CAPABILITIES: Dict[str, Dict[str, Any]] = {
    "qwen3": {"context": 32768, "capabilities": ["coding", "reasoning"], "family": "qwen"},
    "qwen2.5": {"context": 32768, "capabilities": ["coding", "reasoning"], "family": "qwen"},
    "llama3": {"context": 8192, "capabilities": ["coding", "chat"], "family": "llama"},
    "llama3.1": {"context": 128000, "capabilities": ["coding", "reasoning", "chat"], "family": "llama"},
    "llama3.2": {"context": 128000, "capabilities": ["coding", "reasoning", "vision"], "family": "llama"},
    "mistral": {"context": 8192, "capabilities": ["reasoning", "chat"], "family": "mistral"},
    "mixtral": {"context": 32768, "capabilities": ["coding", "reasoning"], "family": "mistral"},
    "codellama": {"context": 16384, "capabilities": ["coding"], "family": "llama"},
    "phi3": {"context": 4096, "capabilities": ["coding", "reasoning"], "family": "phi"},
    "phi4": {"context": 16384, "capabilities": ["coding", "reasoning"], "family": "phi"},
    "gemma2": {"context": 8192, "capabilities": ["chat", "reasoning"], "family": "gemma"},
    "deepseek-coder": {"context": 16384, "capabilities": ["coding"], "family": "deepseek"},
    "deepseek-r1": {"context": 16384, "capabilities": ["coding", "reasoning"], "family": "deepseek"},
    "command-r": {"context": 128000, "capabilities": ["reasoning", "chat"], "family": "cohere"},
    "nomic-embed-text": {"context": 8192, "capabilities": ["embedding"], "family": "nomic"},
    "mxbai-embed-large": {"context": 512, "capabilities": ["embedding"], "family": "mxbai"},
}

# Cloud model defaults
CLOUD_MODEL_DEFAULTS: Dict[str, List[Dict[str, Any]]] = {
    "openai": [
        {"name": "gpt-4o", "context": 128000, "cost": 5.0, "latency": 1.5, "capabilities": ["coding", "reasoning", "vision"]},
        {"name": "gpt-4o-mini", "context": 128000, "cost": 0.5, "latency": 0.8, "capabilities": ["coding", "reasoning"]},
        {"name": "o3-mini", "context": 200000, "cost": 4.0, "latency": 3.0, "capabilities": ["coding", "reasoning"]},
    ],
    "anthropic": [
        {"name": "claude-sonnet-4", "context": 200000, "cost": 3.0, "latency": 2.0, "capabilities": ["coding", "reasoning"]},
        {"name": "claude-haiku-3.5", "context": 200000, "cost": 0.8, "latency": 0.6, "capabilities": ["coding", "reasoning"]},
    ],
    "google": [
        {"name": "gemini-2.0-flash", "context": 1048576, "cost": 0.1, "latency": 0.5, "capabilities": ["coding", "reasoning", "vision"]},
        {"name": "gemini-2.0-pro", "context": 1048576, "cost": 2.0, "latency": 2.0, "capabilities": ["coding", "reasoning", "vision"]},
    ],
    "deepseek": [
        {"name": "deepseek-chat", "context": 64000, "cost": 0.5, "latency": 1.5, "capabilities": ["coding", "reasoning"]},
        {"name": "deepseek-reasoner", "context": 64000, "cost": 2.0, "latency": 3.0, "capabilities": ["reasoning"]},
    ],
}


class ModelDiscovery:
    """Descubre modelos automáticamente del sistema y cloud."""

    def __init__(self, ollama_host: Optional[str] = None):
        self._ollama_host = ollama_host or os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        self._discovered: List[ModelCapability] = []
        self._providers: Dict[str, bool] = {}

    @property
    def discovered(self) -> List[ModelCapability]:
        return list(self._discovered)

    def discover_all(self) -> List[ModelCapability]:
        """Ejecuta todos los discoverers y retorna modelos encontrados."""
        discovered: List[ModelCapability] = []
        discovered.extend(self.discover_ollama())
        discovered.extend(self.discover_cloud())
        self._discovered = discovered
        logger.info("ModelDiscovery: found %d models total", len(discovered))
        return discovered

    def discover_ollama(self) -> List[ModelCapability]:
        """Detecta modelos vía API local de Ollama."""
        models: List[ModelCapability] = []
        try:
            import urllib.request
            url = f"{self._ollama_host}/api/tags"
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode())
                for m in data.get("models", []):
                    name = m.get("name", "")
                    base = name.split(":")[0] if ":" in name else name
                    caps = self._lookup_capabilities(base)
                    models.append(ModelCapability(
                        name=name,
                        provider="ollama",
                        local=True,
                        context_size=caps.get("context", 4096),
                        capabilities=caps.get("capabilities", ["chat"]),
                        model_family=caps.get("family", base),
                    ))
            self._providers["ollama"] = True
            logger.info("Ollama discovery: %d models found", len(models))
        except Exception as e:
            logger.info("Ollama not available: %s", e)
            self._providers["ollama"] = False
        return models

    def discover_lm_studio(self) -> List[ModelCapability]:
        """Detecta modelos vía API de LM Studio."""
        models: List[ModelCapability] = []
        try:
            import urllib.request
            url = "http://localhost:1234/v1/models"
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=2) as resp:
                data = json.loads(resp.read().decode())
                for m in data.get("data", []):
                    mid = m.get("id", "")
                    models.append(ModelCapability(
                        name=mid,
                        provider="lm_studio",
                        local=True,
                        context_size=4096,
                        capabilities=["chat", "reasoning"],
                    ))
            self._providers["lm_studio"] = True
            logger.info("LM Studio discovery: %d models found", len(models))
        except Exception:
            self._providers["lm_studio"] = False
        return models

    def discover_cloud(self) -> List[ModelCapability]:
        """Retorna modelos cloud según var de entorno disponible."""
        models: List[ModelCapability] = []
        for provider, defaults in CLOUD_MODEL_DEFAULTS.items():
            env_key = f"{provider.upper()}_API_KEY"
            if os.environ.get(env_key) or os.environ.get(f"SENTINEL_{env_key}"):
                for m in defaults:
                    models.append(ModelCapability(
                        name=m["name"],
                        provider=provider,
                        local=False,
                        context_size=m["context"],
                        cost=m["cost"],
                        latency_estimate=m["latency"],
                        capabilities=m["capabilities"],
                        model_family=m["name"].split("-")[0],
                    ))
                self._providers[provider] = True
            else:
                self._providers[provider] = False
        return models

    def get_providers(self) -> Dict[str, bool]:
        """Retorna qué proveedores están disponibles."""
        return dict(self._providers)

    def _lookup_capabilities(self, model_name: str) -> Dict[str, Any]:
        """Busca capacidades conocidas para un nombre de modelo."""
        for prefix, caps in OLLAMA_MODEL_CAPABILITIES.items():
            if model_name.startswith(prefix):
                return caps
        return {"context": 4096, "capabilities": ["chat"], "family": model_name}
