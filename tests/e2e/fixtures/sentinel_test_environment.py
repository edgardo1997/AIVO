"""Test environment factory for Sentinel end-to-end tests.

Creates a fully wired SentinelRuntime with lightweight, instrumented
components that capture pipeline state for assertion.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone


# ── Lightweight stub implementations ──────────────────────────────


@dataclass
class StubIntentResult:
    action: str = "query"
    target: str = "general"
    category: str = "CHAT"
    parameters: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.95
    raw_input: str = ""


class StubIntentEngine:
    def __init__(self):
        self.calls: List[str] = []

    def parse(self, utterance: str, context: Optional[Dict[str, Any]] = None) -> StubIntentResult:
        self.calls.append(utterance)
        text = utterance.lower()
        if any(kw in text for kw in ("abre", "open", "launch", "inicia", "ejecuta")):
            return StubIntentResult(action="execute", target="application", category="ACTION", raw_input=utterance)
        if any(kw in text for kw in ("optimiza", "optimize", "gaming", "juego", "rendimiento")):
            return StubIntentResult(action="configure", target="system.performance", category="SYSTEM_OPERATION", raw_input=utterance)
        if any(kw in text for kw in ("continúa", "continue", "proyecto", "project", "siguiente")):
            return StubIntentResult(action="query", target="memory.project", category="MEMORY", raw_input=utterance)
        return StubIntentResult(action="query", target="general", category="CHAT", raw_input=utterance)


class StubContextEngine:
    def __init__(self):
        self.call_count = 0

    async def collect(self, include_processes: Optional[bool] = None) -> Dict[str, Any]:
        self.call_count += 1
        return {
            "cpu": {"cores": 8, "load_percent": 25.0, "frequency_mhz": 3200},
            "memory": {"total_gb": 16.0, "available_gb": 8.5, "percent": 47.0},
            "disk": [{"mount": "C:\\", "total_gb": 512, "used_gb": 200, "free_gb": 312}],
            "gpu": [{"name": "NVIDIA GeForce RTX 3060", "memory_gb": 12, "utilization": 15}],
            "processes": [
                {"name": "explorer.exe", "cpu": 2.0, "memory_mb": 120},
                {"name": "chrome.exe", "cpu": 8.0, "memory_mb": 450},
            ],
            "boot_time": datetime.now(timezone.utc).isoformat(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def to_dict(self) -> Dict[str, Any]:
        return {"collected": True, "call_count": self.call_count}


class StubPlanner:
    def __init__(self):
        self.call_count = 0

    def plan(self, intent: Any, context: Optional[Dict[str, Any]] = None) -> Any:
        self.call_count += 1
        from sentinel.core.planner import Plan, PlanStep

        action = getattr(intent, "action", "query")
        target = getattr(intent, "target", "general")

        if action == "execute" and "application" in target:
            return Plan(
                steps=[
                    PlanStep(id="disc", tool_id="app_discovery", description="Discover Spotify", params={"name": intent.raw_input}),
                    PlanStep(id="launch", tool_id="app_launch", description="Launch Spotify", params={"name": intent.raw_input}),
                ],
                intent=intent,
                risk_score=15,
                estimated_duration_ms=5000,
                description="Launch application",
            )

        if action == "configure" and "performance" in target:
            return Plan(
                steps=[
                    PlanStep(id="snap", tool_id="system_snapshot", description="Create system snapshot", params={}, is_reversible=True),
                    PlanStep(id="opt", tool_id="process_optimizer", description="Optimize for gaming", params={"profile": "gaming"}),
                    PlanStep(id="power", tool_id="power_profile", description="Set high performance power mode", params={"mode": "high_performance"}),
                    PlanStep(id="svc", tool_id="service_optimizer", description="Tune services for gaming", params={"profile": "gaming"}),
                    PlanStep(id="verify", tool_id="verification", description="Verify optimizations", params={}),
                ],
                intent=intent,
                risk_score=30,
                estimated_duration_ms=15000,
                description="PC gaming optimization",
            )

        if "memory" in str(target):
            return Plan(
                steps=[
                    PlanStep(id="recall", tool_id="memory_query", description="Recall Python project context", params={"project": "Python"}),
                    PlanStep(id="rebuild", tool_id="context_rebuild", description="Rebuild context from memory", params={}),
                ],
                intent=intent,
                risk_score=5,
                estimated_duration_ms=3000,
                description="Continue project",
            )

        return Plan(
            steps=[PlanStep(id="resp", tool_id="responder", description="Generate response", params={"message": "Hello"})],
            intent=intent,
            risk_score=0,
            estimated_duration_ms=1000,
            description="Conversation response",
        )


class StubRiskClassifier:
    def __init__(self):
        self.call_count = 0

    def classify(self, intent: Any, plan: Any, context: Optional[Dict[str, Any]] = None) -> Any:
        self.call_count += 1
        from sentinel.core.risk_classifier import RiskClassification

        action = getattr(intent, "action", "query")
        level = "LOW" if action in ("query",) else "MEDIUM" if action in ("configure",) else "LOW"
        return RiskClassification(
            level=level,
            score={"LOW": 10, "MEDIUM": 35, "HIGH": 70}.get(level, 10),
            label=level,
            description=str(action),
            is_read_only=(action == "query"),
            is_reversible=(action != "execute"),
        )


class StubDecisionEngine:
    def __init__(self, mode: str = "approve"):
        self.call_count = 0
        self._mode = mode

    def evaluate(self, plan: Any, context: Optional[Dict[str, Any]] = None, simulation_result: Any = None, risk_classification: Any = None) -> Any:
        self.call_count += 1
        from sentinel.core.decision_engine import DecisionResult, Decision

        if self._mode == "deny":
            return DecisionResult(decision=Decision.REJECT, plan=plan, reason="Test deny policy")
        if self._mode == "require_confirm":
            return DecisionResult(decision=Decision.REQUIRE_CONFIRM, plan=plan, reason="Test requires confirmation")

        return DecisionResult(decision=Decision.APPROVE, plan=plan, reason="Test auto-approve", base_risk_score=getattr(risk_classification, "score", 10) if risk_classification else 10)


class StubPolicyEngine:
    def __init__(self):
        self.calls: List[Dict[str, Any]] = []

    async def evaluate(self, tool_id: str, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None, required_permissions: Optional[List[str]] = None) -> Any:
        self.calls.append({"tool_id": tool_id, "params": params})
        from sentinel.core.policy_engine import PolicyResult

        return PolicyResult(effect="ALLOW", matched_policies=["test_allow_all"], risk_score=10)


class StubConsentService:
    def __init__(self, auto_grant: bool = True):
        self.auto_grant = auto_grant
        self.calls: List[Dict[str, Any]] = []

    async def request_confirmation(self, action_id: str, description: str, risk_level: str, user_id: str, session_id: str, context: Optional[Dict[str, Any]] = None) -> bool:
        self.calls.append({"action_id": action_id, "risk_level": risk_level})
        return self.auto_grant


class StubToolGateway:
    def __init__(self):
        self.executions: List[Dict[str, Any]] = []
        self._tools: Dict[str, Any] = {}
        self._policy_engine: Any = None
        self._audit_service: Any = None

    def register(self, name: str, func: Any) -> None:
        from sentinel.core.tool import Tool

        self._tools[name] = Tool(id=name, name=name, execute_fn=func)

    def get_spec(self, tool_id: str) -> Any:
        from sentinel.core.tool import ToolSpec, ToolStatus

        if tool_id in self._tools:
            tool = self._tools[tool_id]
            return ToolSpec(
                id=tool.id,
                name=tool.name,
                description="Stub e2e tool",
                version="1.0.0",
                parameters={},
                required_permissions=[],
                status=ToolStatus.ACTIVE,
            )
        return ToolSpec(
            id=tool_id,
            name=tool_id,
            description="Stub e2e tool",
            version="1.0.0",
            parameters={},
            required_permissions=[],
            status=ToolStatus.ACTIVE,
        )

    async def execute(self, tool_id: str, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Any:
        from sentinel.core.tool import ToolResult
        import time

        start = time.monotonic()
        self.executions.append({"tool_id": tool_id, "params": params})
        if tool_id in self._tools:
            try:
                result = await self._tools[tool_id].execute(params, context or {})
                elapsed = (time.monotonic() - start) * 1000
                result.duration_ms = elapsed
                return result
            except Exception as e:
                return ToolResult.fail(str(e), tool_id=tool_id, duration_ms=(time.monotonic() - start) * 1000)
        elapsed = (time.monotonic() - start) * 1000
        return ToolResult.ok({f"{tool_id}_executed": True, "tool_id": tool_id}, duration_ms=elapsed)


class StubAuditService:
    def __init__(self):
        self.entries: List[Dict[str, Any]] = []

    def log_action(self, action: str, details: Dict[str, Any], result: str = "success", user_id: str = "") -> None:
        self.entries.append({
            "action": action, "details": details, "result": result, "user_id": user_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def log_gateway_authorization(self, action: str, tool_id: str, approved: bool, identity: str) -> None:
        self.entries.append({
            "action": "gateway.authorization", "tool_id": tool_id, "approved": approved,
            "identity": identity, "timestamp": datetime.now(timezone.utc).isoformat(),
        })


class StubMemory:
    def __init__(self):
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._kv_store: Dict[str, Any] = {}
        self._history: Dict[str, List[Any]] = {}
        self._preferences: Dict[str, Dict[str, Any]] = {}
        self._snapshots: List[Dict[str, Any]] = []

    def create_session(self, session_id: str) -> None:
        self._sessions[session_id] = {"created": datetime.now(timezone.utc).isoformat(), "messages": []}

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        return self._sessions.get(session_id)

    def store(self, key: str, value: Any) -> None:
        self._kv_store[key] = value

    def get(self, key: str) -> Optional[Any]:
        return self._kv_store.get(key)

    def store_preference(self, key: str, value: Any) -> None:
        self._preferences[key] = value

    def get_preferences(self, key: str) -> Optional[Any]:
        return self._preferences.get(key)

    def save_snapshot(self, name: str, data: Dict[str, Any]) -> None:
        self._snapshots.append({"name": name, "data": data, "timestamp": datetime.now(timezone.utc).isoformat()})

    def get_session_history(self, session_id: str, limit: int = 10, user_id: str = "") -> List[Any]:
        return self._history.get(session_id, [])


class StubPerformanceIntelligence:
    def __init__(self):
        self._metrics: List[Any] = []

    def record_metric(self, metric: Any) -> None:
        self._metrics.append(metric)

    def get_summary(self, model_id: Optional[str] = None) -> List[Any]:
        return []

    def get_metrics(self, model_id: Optional[str] = None) -> List[Any]:
        return list(self._metrics)


class StubModelRouter:
    def __init__(self):
        self.calls: List[Any] = []

    def select(self, task_type: Any, context: Optional[Dict[str, Any]] = None) -> Any:
        self.calls.append({"task_type": str(task_type), "context": context})
        from sentinel.core.router_types import RouterDecision, TaskType

        return RouterDecision(provider_id="test_provider", model="test_model", task_type=TaskType.QUICK, strategy="test", reason="e2e test")


class StubRateLimiter:
    def check_hierarchy(self, limits: List[tuple]) -> Any:
        class Allow:
            allowed = True

        return Allow()


# ── Factory ───────────────────────────────────────────────────────


def create_sentinel_runtime(auto_approve: bool = True) -> Any:
    """Create a fully wired SentinelRuntime for end-to-end testing.

    Args:
        auto_approve: If True, consent is automatically granted.

    Returns:
        Configured SentinelRuntime instance with stub components.
    """
    from sentinel.core.runtime import SentinelRuntime
    from sentinel.core.execution_pipeline import ExecutionPipeline
    from sentinel.security.tool_guard import ToolExecutionGuard

    gateway = StubToolGateway()
    audit = StubAuditService()
    consent = StubConsentService(auto_grant=auto_approve)
    guard = ToolExecutionGuard(
        tool_gateway=gateway,
        policy_engine=StubPolicyEngine(),
        audit_service=audit,
        consent_service=consent,
        risk_classifier=StubRiskClassifier(),
    )
    pipeline = ExecutionPipeline(
        tool_gateway=gateway,
        tool_execution_guard=guard,
        audit_service=audit,
    )

    runtime = SentinelRuntime(
        intent_engine=StubIntentEngine(),
        context_engine=StubContextEngine(),
        planner=StubPlanner(),
        risk_classifier=StubRiskClassifier(),
        decision_engine=StubDecisionEngine(),
        policy_engine=StubPolicyEngine(),
        consent_service=consent,
        tool_gateway=gateway,
        audit_service=audit,
        memory=StubMemory(),
        performance_intelligence=StubPerformanceIntelligence(),
        model_router=StubModelRouter(),
        rate_limiter=StubRateLimiter(),
        event_bus=None,
        execution_pipeline=pipeline,
    )
    return runtime


__all__ = [
    "create_sentinel_runtime",
    "StubIntentEngine", "StubIntentResult",
    "StubContextEngine", "StubPlanner",
    "StubRiskClassifier", "StubDecisionEngine",
    "StubPolicyEngine", "StubConsentService",
    "StubToolGateway", "StubAuditService",
    "StubMemory", "StubPerformanceIntelligence",
    "StubModelRouter", "StubRateLimiter",
]
