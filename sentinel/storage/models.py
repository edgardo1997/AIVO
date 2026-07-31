"""Modelos de datos para almacenamiento persistente.

Cada modelo corresponde a una tabla en la base de datos.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _s(value: Any) -> str:
    """Coerce enums (e.g. TaskType) and other values to a plain string."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if hasattr(value, "value"):
        return str(value.value)
    return str(value)


def _id() -> str:
    import uuid
    return uuid.uuid4().hex[:16]


@dataclass
class StoredModel:
    name: str
    provider: str
    local: bool = True
    capabilities: List[str] = field(default_factory=list)
    context_size: int = 4096
    cost: float = 0.0
    latency_estimate: float = 1.0
    last_seen: str = ""
    created_at: str = ""
    id: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = f"mod_{_id()}"
        if not self.last_seen:
            self.last_seen = _now()
        if not self.created_at:
            self.created_at = _now()

    def to_row(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "provider": self.provider,
            "local": 1 if self.local else 0,
            "capabilities": json.dumps(self.capabilities),
            "context_size": self.context_size,
            "cost": self.cost,
            "latency_estimate": self.latency_estimate,
            "last_seen": self.last_seen,
            "created_at": self.created_at,
        }

    @staticmethod
    def from_row(row: Dict[str, Any]) -> StoredModel:
        caps = row.get("capabilities", "[]")
        if isinstance(caps, str):
            caps = json.loads(caps)
        return StoredModel(
            id=row["id"],
            name=row["name"],
            provider=row["provider"],
            local=bool(row.get("local", 1)),
            capabilities=caps,
            context_size=row.get("context_size", 4096),
            cost=row.get("cost", 0.0),
            latency_estimate=row.get("latency_estimate", 1.0),
            last_seen=row.get("last_seen", ""),
            created_at=row.get("created_at", ""),
        )


@dataclass
class FeedbackRecord:
    model_id: str
    task_type: str
    success: bool
    quality_score: float = 0.5
    latency: float = 0.0
    error: Optional[str] = None
    user_id: str = ""
    session_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    id: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = f"fb_{_id()}"
        if not self.created_at:
            self.created_at = _now()

    def to_row(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "model_id": self.model_id,
            "task_type": _s(self.task_type),
            "success": 1 if self.success else 0,
            "quality_score": self.quality_score,
            "latency": self.latency,
            "error": self.error,
            "user_id": _s(self.user_id),
            "session_id": _s(self.session_id),
            "metadata": json.dumps(self.metadata),
            "created_at": self.created_at,
        }

    @staticmethod
    def from_row(row: Dict[str, Any]) -> FeedbackRecord:
        meta = row.get("metadata", "{}")
        if isinstance(meta, str):
            meta = json.loads(meta) if meta else {}
        return FeedbackRecord(
            id=row["id"],
            model_id=row["model_id"],
            task_type=row["task_type"],
            success=bool(row.get("success", 1)),
            quality_score=row.get("quality_score", 0.5),
            latency=row.get("latency", 0.0),
            error=row.get("error"),
            user_id=row.get("user_id", ""),
            session_id=row.get("session_id", ""),
            metadata=meta,
            created_at=row.get("created_at", ""),
        )


@dataclass
class MetricRecord:
    component: str
    metric_name: str
    value: float
    unit: str = ""
    tags: Dict[str, str] = field(default_factory=dict)
    timestamp: str = ""
    id: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = f"m_{_id()}"
        if not self.timestamp:
            self.timestamp = _now()

    def to_row(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "component": self.component,
            "metric_name": self.metric_name,
            "value": self.value,
            "unit": self.unit,
            "tags": json.dumps(self.tags),
            "timestamp": self.timestamp,
        }

    @staticmethod
    def from_row(row: Dict[str, Any]) -> MetricRecord:
        tags = row.get("tags", "{}")
        if isinstance(tags, str):
            tags = json.loads(tags) if tags else {}
        return MetricRecord(
            id=row["id"],
            component=row["component"],
            metric_name=row["metric_name"],
            value=row["value"],
            unit=row.get("unit", ""),
            tags=tags,
            timestamp=row.get("timestamp", ""),
        )


@dataclass
class ConversationRecord:
    session_id: str
    message_id: str = ""
    role: str = ""
    content: str = ""
    context: Dict[str, Any] = field(default_factory=dict)
    model_id: str = ""
    created_at: str = ""

    def __post_init__(self):
        if not self.message_id:
            self.message_id = f"msg_{_id()}"
        if not self.created_at:
            self.created_at = _now()

    def to_row(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "message_id": self.message_id,
            "role": self.role,
            "content": self.content,
            "context": json.dumps(self.context),
            "model_id": self.model_id,
            "created_at": self.created_at,
        }

    @staticmethod
    def from_row(row: Dict[str, Any]) -> ConversationRecord:
        ctx = row.get("context", "{}")
        if isinstance(ctx, str):
            ctx = json.loads(ctx) if ctx else {}
        return ConversationRecord(
            session_id=row["session_id"],
            message_id=row["message_id"],
            role=row.get("role", ""),
            content=row.get("content", ""),
            context=ctx,
            model_id=row.get("model_id", ""),
            created_at=row.get("created_at", ""),
        )


@dataclass
class DecisionRecord:
    request: str
    decision: str
    risk_level: str = ""
    selected_model: str = ""
    intent: str = ""
    reason: str = ""
    execution_id: str = ""
    created_at: str = ""
    id: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = f"dec_{_id()}"
        if not self.created_at:
            self.created_at = _now()

    def to_row(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "request": self.request[:500],
            "intent": self.intent,
            "decision": self.decision,
            "risk_level": self.risk_level,
            "selected_model": self.selected_model,
            "reason": self.reason[:500],
            "execution_id": self.execution_id,
            "created_at": self.created_at,
        }

    @staticmethod
    def from_row(row: Dict[str, Any]) -> DecisionRecord:
        return DecisionRecord(
            id=row["id"],
            request=row["request"],
            intent=row.get("intent", ""),
            decision=row["decision"],
            risk_level=row.get("risk_level", ""),
            selected_model=row.get("selected_model", ""),
            reason=row.get("reason", ""),
            execution_id=row.get("execution_id", ""),
            created_at=row.get("created_at", ""),
        )


@dataclass
class StoredExecution:
    execution_id: str
    timestamp: str = ""
    user_request: str = ""
    intent: str = ""
    task_type: str = ""
    selected_model: str = ""
    tools_used: List[str] = field(default_factory=list)
    duration: float = 0.0
    success: bool = True
    failure_reason: Optional[str] = None
    risk_level: str = ""
    cost: float = 0.0
    confidence_score: float = 0.0
    error: Optional[str] = None

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = _now()

    def to_row(self) -> Dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "timestamp": self.timestamp,
            "user_request": _s(self.user_request)[:2000],
            "intent": _s(self.intent)[:200],
            "task_type": _s(self.task_type)[:200],
            "selected_model": _s(self.selected_model)[:200],
            "tools_used": json.dumps([_s(t) for t in self.tools_used]),
            "duration": self.duration,
            "success": 1 if self.success else 0,
            "failure_reason": _s(self.failure_reason)[:2000] if self.failure_reason else None,
            "risk_level": _s(self.risk_level)[:50],
            "cost": self.cost,
            "confidence_score": self.confidence_score,
            "error": _s(self.error)[:2000] if self.error else None,
        }

    @staticmethod
    def from_row(row: Dict[str, Any]) -> StoredExecution:
        tools = row.get("tools_used", "[]")
        if isinstance(tools, str):
            tools = json.loads(tools) if tools else []
        return StoredExecution(
            execution_id=row["execution_id"],
            timestamp=row.get("timestamp", ""),
            user_request=row.get("user_request", ""),
            intent=row.get("intent", ""),
            task_type=row.get("task_type", ""),
            selected_model=row.get("selected_model", ""),
            tools_used=tools,
            duration=row.get("duration", 0.0),
            success=bool(row.get("success", 1)),
            failure_reason=row.get("failure_reason"),
            risk_level=row.get("risk_level", ""),
            cost=row.get("cost", 0.0),
            confidence_score=row.get("confidence_score", 0.0),
            error=row.get("error"),
        )


@dataclass
class ModelPerformanceEvent:
    model_name: str
    task_type: str
    latency: float = 0.0
    success: bool = True
    quality_score: float = 0.5
    resource_usage: float = 0.0
    tokens_used: int = 0
    cost: float = 0.0
    created_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = _now()

    def to_row(self) -> Dict[str, Any]:
        return {
            "model_name": self.model_name,
            "task_type": _s(self.task_type),
            "latency": self.latency,
            "success": 1 if self.success else 0,
            "quality_score": self.quality_score,
            "resource_usage": self.resource_usage,
            "tokens_used": self.tokens_used,
            "cost": self.cost,
            "created_at": self.created_at,
        }

    @staticmethod
    def from_row(row: Dict[str, Any]) -> ModelPerformanceEvent:
        return ModelPerformanceEvent(
            model_name=row["model_name"],
            task_type=row.get("task_type", ""),
            latency=row.get("latency", 0.0),
            success=bool(row.get("success", 1)),
            quality_score=row.get("quality_score", 0.5),
            resource_usage=row.get("resource_usage", 0.0),
            tokens_used=row.get("tokens_used", 0),
            cost=row.get("cost", 0.0),
            created_at=row.get("created_at", ""),
        )


@dataclass
class UserPreference:
    user_id: str
    key: str
    value: Any
    source: str = "observed"
    evidence_count: int = 1
    confidence: float = 0.5
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        now = _now()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now

    def to_row(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "key": self.key,
            "value": json.dumps(self.value),
            "source": self.source,
            "evidence_count": self.evidence_count,
            "confidence": self.confidence,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @staticmethod
    def from_row(row: Dict[str, Any]) -> UserPreference:
        value = row.get("value", "null")
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except (ValueError, TypeError):
                value = value
        return UserPreference(
            user_id=row["user_id"],
            key=row["key"],
            value=value,
            source=row.get("source", "observed"),
            evidence_count=row.get("evidence_count", 1),
            confidence=row.get("confidence", 0.5),
            created_at=row.get("created_at", ""),
            updated_at=row.get("updated_at", ""),
        )
