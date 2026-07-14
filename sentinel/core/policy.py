from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict


class PolicyEffect(Enum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_CONFIRM = "require_confirm"


@dataclass
class PolicyResult:
    effect: PolicyEffect
    policy_id: str
    reason: str
    context: Dict[str, Any] = field(default_factory=dict)


class Policy(ABC):
    @abstractmethod
    def policy_id(self) -> str:
        ...

    @abstractmethod
    def description(self) -> str:
        ...

    @abstractmethod
    async def evaluate(
        self,
        tool_id: str,
        params: Dict[str, Any],
        context: Dict[str, Any],
    ) -> PolicyResult:
        ...
