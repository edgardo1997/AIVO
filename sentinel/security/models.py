"""Security models for tool execution boundary."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class RiskLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SecurityDecision(Enum):
    APPROVED = "approved"
    DENIED = "denied"
    REQUIRE_CONFIRMATION = "require_confirmation"


@dataclass
class ToolRequest:
    tool_name: str
    arguments: Dict[str, Any]
    source: str
    user_context: Dict[str, Any] = field(default_factory=dict)
    session_id: str = ""
    user_id: str = ""
    execution_id: str = ""
    model_id: str = ""
    provider_id: str = ""
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "arguments": dict(self.arguments),
            "source": self.source,
            "user_context": dict(self.user_context),
            "session_id": self.session_id,
            "user_id": self.user_id,
            "execution_id": self.execution_id,
            "model_id": self.model_id,
            "provider_id": self.provider_id,
            "timestamp": self.timestamp,
        }


@dataclass
class ExecutionResult:
    success: bool
    data: Any = None
    error: Optional[str] = None
    risk_level: RiskLevel = RiskLevel.LOW
    decision: SecurityDecision = SecurityDecision.APPROVED
    policy_id: Optional[str] = None
    policy_reason: Optional[str] = None
    user_confirmed: bool = False
    audit_entry: Optional[Dict[str, Any]] = None
    duration_ms: float = 0.0
    tool_name: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "risk_level": self.risk_level.value,
            "decision": self.decision.value,
            "policy_id": self.policy_id,
            "policy_reason": self.policy_reason,
            "user_confirmed": self.user_confirmed,
            "audit_entry": self.audit_entry,
            "duration_ms": self.duration_ms,
            "tool_name": self.tool_name,
        }
