from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class ModelStatus(Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    DEPRECATED = "deprecated"
    EXPERIMENTAL = "experimental"


@dataclass(frozen=True)
class ModelMetadata:
    id: str
    provider: str
    context_window: int = 4096
    supports_tool_calling: bool = False
    supports_vision: bool = False
    supports_coding: bool = False
    supports_reasoning: bool = False
    supports_embeddings: bool = False
    speed: str = "unknown"
    cost: float = 0.0
    local: bool = False
    status: ModelStatus = ModelStatus.AVAILABLE
    description: str = ""
    tags: List[str] = field(default_factory=list)
    config: Dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id or not self.id.strip():
            raise ValueError("ModelMetadata 'id' must be a non-empty string")
        if not self.provider or not self.provider.strip():
            raise ValueError("ModelMetadata 'provider' must be a non-empty string")
        if self.context_window < 1:
            raise ValueError("ModelMetadata 'context_window' must be >= 1")
        if self.cost < 0:
            raise ValueError("ModelMetadata 'cost' must be >= 0")

    @property
    def display_name(self) -> str:
        return f"{self.provider}/{self.id}"

    @property
    def is_available(self) -> bool:
        return self.status == ModelStatus.AVAILABLE

    def has_capability(self, capability: str) -> bool:
        cap_map = {
            "tool_calling": self.supports_tool_calling,
            "vision": self.supports_vision,
            "coding": self.supports_coding,
            "reasoning": self.supports_reasoning,
            "embeddings": self.supports_embeddings,
            "local": self.local,
        }
        if capability in cap_map:
            return cap_map[capability]
        return True
