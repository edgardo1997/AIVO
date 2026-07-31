from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Union

from sentinel.core.intent import Intent

import logging

logger = logging.getLogger(__name__)


class IntentType(Enum):
    CHAT = "CHAT"
    ACTION = "ACTION"
    CODING = "CODING"
    DOCUMENT = "DOCUMENT"
    SEARCH = "SEARCH"
    UNKNOWN = "UNKNOWN"


INTENT_CAPABILITY_MAP: Dict[IntentType, List[str]] = {
    IntentType.CHAT: [
        "conversation",
        "personality",
    ],
    IntentType.ACTION: [
        "tool_calling",
        "system_access",
        "risk_analysis",
    ],
    IntentType.CODING: [
        "coding",
        "reasoning",
    ],
    IntentType.DOCUMENT: [
        "vision",
        "long_context",
    ],
    IntentType.SEARCH: [
        "internet",
        "grounding",
    ],
    IntentType.UNKNOWN: [
        "conversation",
    ],
}

_INTENT_ACTION_MAP: Dict[str, IntentType] = {
    "execute": IntentType.ACTION,
    "launch": IntentType.ACTION,
    "analyze": IntentType.CODING,
    "diagnose": IntentType.CODING,
    "query": IntentType.SEARCH,
    "search": IntentType.SEARCH,
    "configure": IntentType.CHAT,
    "config": IntentType.CHAT,
    "chat": IntentType.CHAT,
    "talk": IntentType.CHAT,
    "read": IntentType.DOCUMENT,
    "document": IntentType.DOCUMENT,
    "vision": IntentType.DOCUMENT,
}


@dataclass
class CapabilitySet:
    capabilities: Set[str] = field(default_factory=set)

    def __init__(self, capabilities: Optional[List[str]] = None):
        self.capabilities = set(capabilities) if capabilities else set()

    def has(self, capability: str) -> bool:
        return capability in self.capabilities

    def has_all(self, required: List[str]) -> bool:
        return all(c in self.capabilities for c in required)

    def has_any(self, candidates: List[str]) -> bool:
        return any(c in self.capabilities for c in candidates)

    def add(self, capability: str) -> None:
        self.capabilities.add(capability)

    def add_all(self, capabilities: List[str]) -> None:
        self.capabilities.update(capabilities)

    def remove(self, capability: str) -> None:
        self.capabilities.discard(capability)

    def merge(self, other: "CapabilitySet") -> "CapabilitySet":
        merged = CapabilitySet(list(self.capabilities))
        merged.capabilities.update(other.capabilities)
        return merged

    def to_list(self) -> List[str]:
        return sorted(self.capabilities)

    def to_dict(self) -> Dict[str, bool]:
        return {c: True for c in self.capabilities}

    def __contains__(self, capability: str) -> bool:
        return self.has(capability)

    def __len__(self) -> int:
        return len(self.capabilities)

    def __iter__(self):
        return iter(self.capabilities)

    def __repr__(self) -> str:
        return f"CapabilitySet({sorted(self.capabilities)})"


class CapabilityEngine:
    def __init__(self, custom_map: Optional[Dict[IntentType, List[str]]] = None):
        self._map: Dict[IntentType, List[str]] = dict(INTENT_CAPABILITY_MAP)
        if custom_map:
            self._map.update(custom_map)

    def resolve(self, intent: Union[IntentType, Intent, str]) -> CapabilitySet:
        intent_type = self._to_intent_type(intent)
        caps = self._map.get(intent_type, self._map[IntentType.UNKNOWN])
        logger.debug(
            "CapabilityEngine: %s -> %s -> %s",
            intent, intent_type.value if isinstance(intent_type, IntentType) else "?", caps,
        )
        return CapabilitySet(list(caps))

    def _to_intent_type(self, intent: Union[IntentType, Intent, str]) -> IntentType:
        if isinstance(intent, IntentType):
            return intent
        if isinstance(intent, Intent):
            mapped = _INTENT_ACTION_MAP.get(intent.action.lower())
            if mapped:
                return mapped
            logger.debug("Unknown Intent action '%s' — falling back to CHAT", intent.action)
            return IntentType.CHAT
        if isinstance(intent, str):
            intent_upper = intent.upper().strip()
            for it in IntentType:
                if it.value == intent_upper:
                    return it
            mapped = _INTENT_ACTION_MAP.get(intent.lower())
            if mapped:
                return mapped
            logger.debug("Unknown intent string '%s' — falling back to CHAT", intent)
            return IntentType.CHAT
        logger.warning("Unrecognized intent type %s — falling back to CHAT", type(intent).__name__)
        return IntentType.CHAT

    def get_capabilities_for(self, intent_type: IntentType) -> List[str]:
        return list(self._map.get(intent_type, self._map[IntentType.UNKNOWN]))

    def register_intent_mapping(self, intent_type: IntentType, capabilities: List[str]) -> None:
        self._map[intent_type] = list(capabilities)
        logger.info("CapabilityEngine: registered mapping %s -> %s", intent_type.value, capabilities)

    def list_registered_intents(self) -> List[Dict[str, Any]]:
        return [
            {"intent": it.value, "capabilities": list(caps)}
            for it, caps in self._map.items()
        ]
