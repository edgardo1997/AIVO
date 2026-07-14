from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .recovery import RecoveryPolicy
import uuid


class ToolStatus(Enum):
    ACTIVE = "active"
    DISABLED = "disabled"


@dataclass
class ToolSpec:
    id: str
    name: str
    description: str
    version: str
    parameters: Dict[str, Any]
    required_permissions: List[str]
    timeout_seconds: int = 30
    status: ToolStatus = ToolStatus.ACTIVE
    category: str = "general"
    recovery_policy: Optional["RecoveryPolicy"] = None


@dataclass
class ToolResult:
    success: bool
    data: Any = None
    error: Optional[str] = None
    tool_id: str = ""
    execution_id: str = ""
    duration_ms: Optional[float] = None
    timestamp: str = ""
    requires_confirmation: bool = False
    policy_decision: Optional[str] = None
    policy_result: Optional[Dict[str, Any]] = None
    quality_result: Optional[Dict[str, Any]] = None

    @staticmethod
    def ok(data: Any, tool_id: str = "", duration_ms: Optional[float] = None) -> "ToolResult":
        return ToolResult(
            success=True,
            data=data,
            tool_id=tool_id,
            execution_id=uuid.uuid4().hex[:12],
            duration_ms=duration_ms,
            timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        )

    @staticmethod
    def fail(error: str, tool_id: str = "", duration_ms: Optional[float] = None) -> "ToolResult":
        return ToolResult(
            success=False,
            error=error,
            tool_id=tool_id,
            execution_id=uuid.uuid4().hex[:12],
            duration_ms=duration_ms,
            timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        )

    @staticmethod
    def needs_confirm(
        reason: str,
        tool_id: str = "",
        policy_id: str = "",
    ) -> "ToolResult":
        return ToolResult(
            success=False,
            error=reason,
            tool_id=tool_id,
            execution_id=uuid.uuid4().hex[:12],
            timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            requires_confirmation=True,
            policy_decision=policy_id,
        )


class Tool(ABC):
    @abstractmethod
    def spec(self) -> ToolSpec: ...

    @abstractmethod
    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult: ...
