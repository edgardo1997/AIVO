from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol


class ConversationMode(str, Enum):
    ADVANCED = "advanced"
    CORE = "core"


@dataclass(frozen=True)
class ConversationRequest:
    message: str
    context: List[Dict[str, str]] = field(default_factory=list)
    purpose: str = "conversation"
    tool_result: Optional[Any] = None


@dataclass(frozen=True)
class ConversationResponse:
    text: str
    mode: ConversationMode
    provider: Optional[str] = None
    model: Optional[str] = None
    capabilities: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "response": self.text,
            "provider": self.provider,
            "model": self.model,
            "conversation_mode": self.mode.value,
            "capabilities": self.capabilities,
        }


class CoreConversation(Protocol):
    def respond(self, request: ConversationRequest, capabilities: Dict[str, Any]) -> str: ...


class CapabilitySource(Protocol):
    def snapshot(self) -> Dict[str, Any]: ...
