"""Canonical provider and model registry with read-only metadata resolution."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sentinel.core.model_schemas import ModelCapability, ModelCandidate, CapabilityStatus
from sentinel.core.model_registry import ModelRegistry
from sentinel.core.router_types import BUILTIN_PROVIDERS, ProviderSpec


class ProviderRegistry:
    """Read-only registry: adapters, providers, models, capabilities.

    Does not authorize, budget, route, execute, or persist keys.
    """

    def __init__(self, providers: Optional[List[ProviderSpec]] = None, model_registry: Optional[ModelRegistry] = None):
        self._providers: Dict[str, ProviderSpec] = {p.id: p for p in (providers or BUILTIN_PROVIDERS)}
        self._model_registry = model_registry or ModelRegistry()

    def list_providers(self) -> List[ProviderSpec]:
        return list(self._providers.values())

    def get_provider(self, provider_id: str) -> Optional[ProviderSpec]:
        return self._providers.get(provider_id)

    def list_models(self, provider_id: Optional[str] = None) -> List[ModelCandidate]:
        models: List[ModelCandidate] = []
        for pid, spec in self._providers.items():
            if provider_id is not None and pid != provider_id:
                continue
            models.append(
                ModelCandidate(
                    provider_id=pid,
                    model_id=spec.default_model,
                    model_name=spec.default_model,
                    is_local=spec.is_local,
                    is_cloud=not spec.is_local,
                    capabilities=self._resolve_capabilities(spec),
                )
            )
            for mid in getattr(spec, "models", []):
                if mid == spec.default_model:
                    continue
                models.append(
                    ModelCandidate(
                        provider_id=pid,
                        model_id=mid,
                        model_name=mid,
                        is_local=spec.is_local,
                        is_cloud=not spec.is_local,
                        capabilities=self._resolve_capabilities(spec),
                    )
                )
        return models

    def resolve_model(self, provider_id: str, model_id: str) -> Optional[ModelCandidate]:
        for m in self.list_models(provider_id):
            if m.model_id == model_id:
                return m
        return None

    def _resolve_capabilities(self, spec: ProviderSpec) -> List[ModelCapability]:
        caps: List[ModelCapability] = []
        if spec.is_local:
            caps.append(ModelCapability(name="local", status=CapabilityStatus.DECLARED))
        else:
            caps.append(ModelCapability(name="cloud", status=CapabilityStatus.DECLARED))
        for cap in ["chat", "tool_calling", "vision", "streaming"]:
            caps.append(ModelCapability(name=cap, status=CapabilityStatus.DECLARED))
        return caps

    def get_model_registry(self) -> ModelRegistry:
        return self._model_registry
