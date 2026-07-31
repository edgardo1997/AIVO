"""FASE 6 — Real production harness.

Builds the REAL production stack — no SentinelRuntime, no stubs, no mocks:
Orchestrator, ToolGateway, ExecutionPipeline, ToolExecutionGuard,
IntelligenceCoordinator, StorageEngine (SQLite), ModelRouter, PolicyEngine,
AuditService, ConfirmationBroker — all real classes wired as in production.

Only the *test scenario tools* are defined here, and they are real `Tool`
subclasses that perform real work (no MagicMock).
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from sentinel.core import DecisionEngine, IntentEngine, ModelRouter, Orchestrator, Planner
from sentinel.core.confirmation import ConfirmationBroker
from sentinel.core.context import ContextEngine
from sentinel.core.event_bus import EventBus
from sentinel.core.execution_pipeline import ExecutionPipeline
from sentinel.core.intelligence_coordinator import IntelligenceCoordinator
from sentinel.core.model_registry import ModelRegistry
from sentinel.core.operational_memory import SQLiteBackend
from sentinel.core.policy import Policy, PolicyEffect, PolicyResult
from sentinel.core.policy_engine import PolicyEngine
from sentinel.core.tool import Tool, ToolResult, ToolSpec
from sentinel.core.tool_gateway import ToolGateway
from sentinel.models.default_registry import build_default_registry
from sentinel.observability.engine import ObservabilityConfig, ObservabilityEngine
from sentinel.security.argument_validator import ArgumentValidator
from sentinel.security.tool_guard import ToolExecutionGuard
from sentinel.security.tool_rate_limiter import ToolRateLimiter
from sentinel.storage import StorageConfig, StorageEngine
from sentinel.storage.repositories.execution_repository import ExecutionRepository
from sentinel.storage.repositories.feedback_repository import FeedbackRepository
from sentinel.storage.repositories.metric_repository import MetricRepository
from sentinel.storage.repositories.model_performance_repository import ModelPerformanceRepository
from sentinel.storage.repositories.model_repository import ModelRepository
from sentinel.storage.repositories.user_preference_repository import UserPreferenceRepository
from sentinel.tools.system_tools import CpuInfoTool, MemoryInfoTool, SystemInfoTool

IDENTITY = {
    "user_id": "production-tester",
    "is_authenticated": True,
    "session_id": "production-session",
    "role": "user",
    "name": "Production Tester",
}

ALLOWED_PERMISSIONS = [
    "system.read",
    "tools.echo",
    "tools.math",
    "tools.crash",
    "config.write",
    "config.confirm",
    "executor.launch",
]


class AllowPolicy(Policy):
    """Real policy: allows any tool whose required permissions are granted."""

    def __init__(self, granted: List[str]):
        self._granted = set(granted)

    def policy_id(self) -> str:
        return "production-allow"

    def description(self) -> str:
        return "Allows the granted production permissions"

    async def evaluate(self, tool_id: str, params: Dict[str, Any], context: Dict[str, Any]) -> PolicyResult:
        required = set(context.get("required_permissions", []))
        if required and required.issubset(self._granted):
            return PolicyResult(effect=PolicyEffect.ALLOW, policy_id=self.policy_id(), reason="permission granted")
        missing = sorted(required - self._granted)
        return PolicyResult(
            effect=PolicyEffect.DENY,
            policy_id=self.policy_id(),
            reason=f"missing permissions: {missing}",
            context={"missing": missing},
        )


class ConfirmPolicy(Policy):
    """Real policy: requires explicit consent before executing."""

    def policy_id(self) -> str:
        return "production-confirm"

    def description(self) -> str:
        return "Requires explicit confirmation for config.confirm"

    async def evaluate(self, tool_id: str, params: Dict[str, Any], context: Dict[str, Any]) -> PolicyResult:
        return PolicyResult(
            effect=PolicyEffect.REQUIRE_CONFIRM,
            policy_id=self.policy_id(),
            reason="explicit consent required",
            context={"tool_id": tool_id},
        )


class EchoTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="tools.echo",
            name="Echo",
            description="Echoes back the provided message",
            version="1.0.0",
            parameters={"message": {"type": "string", "description": "Message to echo"}},
            required_permissions=["tools.echo"],
            category="test",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        message = params.get("message", "")
        return ToolResult.ok(data={"echo": message}, tool_id="tools.echo")


class CalculatorTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="tools.math.add",
            name="Add",
            description="Adds two numbers",
            version="1.0.0",
            parameters={
                "a": {"type": "number", "description": "first operand"},
                "b": {"type": "number", "description": "second operand"},
            },
            required_permissions=["tools.math"],
            category="test",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        a = params.get("a")
        b = params.get("b")
        if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
            return ToolResult.fail(error="a and b must be numbers", tool_id="tools.math.add")
        return ToolResult.ok(data={"sum": a + b}, tool_id="tools.math.add")


class CrashTool(Tool):
    """Real tool that simulates a runtime crash (for chaos scenario 3)."""

    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="tools.crash",
            name="Crash",
            description="Raises a RuntimeError to simulate a tool crash",
            version="1.0.0",
            parameters={},
            required_permissions=["tools.crash"],
            category="test",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        raise RuntimeError("simulated tool crash")


class ConfigWriteTool(Tool):
    """Real tool: writes JSON config to disk inside a temp workspace.

    Keeps the previous content so a rollback can restore state.
    """

    def __init__(self, workspace: Path):
        self._workspace = workspace
        self._workspace.mkdir(parents=True, exist_ok=True)
        self._last_backup: Dict[str, Optional[str]] = {}

    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="config.write",
            name="Config Write",
            description="Writes a JSON config file inside the temp workspace",
            version="1.0.0",
            parameters={
                "name": {"type": "string", "description": "config file name"},
                "content": {"type": "object", "description": "JSON content"},
            },
            required_permissions=["config.write"],
            category="test",
        )

    def _resolve(self, name: str) -> Path:
        target = (self._workspace / name).resolve()
        if not str(target).startswith(str(self._workspace.resolve())):
            raise PermissionError(f"path traversal blocked: {name}")
        return target

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        name = params.get("name")
        content = params.get("content")
        if not name or not isinstance(name, str):
            return ToolResult.fail(error="name is required", tool_id="config.write")
        try:
            target = self._resolve(name)
        except PermissionError as exc:
            return ToolResult.fail(error=str(exc), tool_id="config.write")
        previous = None
        if target.exists():
            previous = target.read_text(encoding="utf-8")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(content, ensure_ascii=False), encoding="utf-8")
        self._last_backup[str(target)] = previous
        return ToolResult.ok(data={"path": str(target)}, tool_id="config.write")

    def rollback(self, name: str) -> bool:
        target = self._resolve(name)
        previous = self._last_backup.get(str(target), None)
        if previous is None:
            if target.exists():
                target.unlink()
            return False
        target.write_text(previous, encoding="utf-8")
        return True


class ConfirmTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="config.confirm",
            name="Confirm",
            description="Tool that always requires explicit consent",
            version="1.0.0",
            parameters={"value": {"type": "string"}},
            required_permissions=["config.confirm"],
            category="test",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        return ToolResult.ok(data={"confirmed": params.get("value")}, tool_id="config.confirm")


@dataclass
class ProductionStack:
    gateway: ToolGateway
    policy_engine: PolicyEngine
    audit_service: Any
    memory: SQLiteBackend
    confirmation_broker: ConfirmationBroker
    guard: ToolExecutionGuard
    pipeline: ExecutionPipeline
    intel: IntelligenceCoordinator
    storage: StorageEngine
    router: ModelRouter
    registry: ModelRegistry
    orchestrator: Orchestrator
    workspace: Path
    config_tool: ConfigWriteTool
    observability: Any = None
    metrics: Dict[str, Any] = field(default_factory=dict)

    async def initialize(self) -> None:
        """Mirror production startup: init storage, wire repos, recover learning."""
        await self.storage.initialize()
        try:
            await self.intel.load_registry_from_repository()
        except Exception:
            pass
        try:
            await self.intel.recover_learning()
        except Exception:
            pass

    async def close(self) -> None:
        try:
            self.orchestrator.close()
        except Exception:
            pass
        try:
            self.memory.close()
        except Exception:
            pass
        try:
            await self.storage.close()
        except Exception:
            pass


def build_production_stack(tmp_path: Path, *, enable_confirm: bool = True) -> ProductionStack:
    """Construct the real production stack wired exactly like the sidecar.

    Caller must `await stack.initialize()` before use.
    """

    workspace = Path(tmp_path) / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    registry = build_default_registry() or ModelRegistry()

    from repositories.database import DatabaseManager
    from services.audit_service import AuditService
    from repositories.audit_repository import AuditRepository

    audit_service = AuditService(AuditRepository(DatabaseManager()))
    memory = SQLiteBackend()
    confirmation_broker = ConfirmationBroker(memory)

    policy_engine = PolicyEngine(default_effect=PolicyEffect.DENY)
    policy_engine.register(AllowPolicy(ALLOWED_PERMISSIONS), permissions=ALLOWED_PERMISSIONS)
    if enable_confirm:
        policy_engine.register(ConfirmPolicy(), permissions=["config.confirm"])

    gateway = ToolGateway(policy_engine=policy_engine)
    gateway.set_context_engine(ContextEngine(collect_processes=False))
    gateway.set_event_bus(EventBus())
    gateway.set_audit_service(audit_service)
    gateway.set_confirmation_broker(confirmation_broker)

    observability = ObservabilityEngine(
        ObservabilityConfig(
            backup_dir=str(Path(tmp_path) / "backups"),
            version="production-test",
        )
    )
    gateway.set_observability(observability)

    config_tool = ConfigWriteTool(workspace)
    for tool in (SystemInfoTool(), CpuInfoTool(), MemoryInfoTool(), EchoTool(), CalculatorTool(), CrashTool(), config_tool, ConfirmTool()):
        gateway.register(tool)

    from modules import _ToolAdapter
    from services.executor_service import ExecutorService

    executor = ExecutorService()
    executor.set_audit_service(audit_service)
    gateway.register(_ToolAdapter(executor, "spec_launch", "execute_launch", "executor.launch"))

    guard = ToolExecutionGuard(
        tool_gateway=gateway,
        policy_engine=policy_engine,
        audit_service=audit_service,
        argument_validator=ArgumentValidator(),
        rate_limiter=ToolRateLimiter(),
    )
    pipeline = ExecutionPipeline(
        tool_gateway=gateway,
        tool_execution_guard=guard,
        audit_service=audit_service,
    )

    storage = StorageEngine(StorageConfig(database_url=f"sqlite:///{Path(tmp_path) / 'sentinel.db'}", migrate_on_start=True))
    intel = IntelligenceCoordinator(model_registry=registry)
    intel.set_model_registry(registry)
    intel.set_model_repository(ModelRepository(storage))
    intel.set_metric_repository(MetricRepository(storage))
    intel.set_feedback_repository(FeedbackRepository(storage))
    intel.set_execution_repository(ExecutionRepository(storage))
    intel.set_model_performance_repository(ModelPerformanceRepository(storage))
    intel.set_user_preference_repository(UserPreferenceRepository(storage))

    router = ModelRouter()
    router.set_model_registry(registry)
    router.set_intelligence(intel)
    intel.set_model_router(router)
    try:
        router.set_failure_reporter(lambda provider_id, model, classification: observability.record_provider_failure(provider_id))
    except Exception:
        pass

    orchestrator = Orchestrator(
        intent_engine=IntentEngine(),
        tool_gateway=gateway,
        planner=Planner(),
        decision_engine=DecisionEngine(),
        model_router=router,
        context_engine=ContextEngine(collect_processes=False),
        memory=memory,
        audit_service=audit_service,
        execution_pipeline=pipeline,
        intelligence=intel,
        process_timeout=30.0,
        observability_engine=observability,
    )

    return ProductionStack(
        gateway=gateway,
        policy_engine=policy_engine,
        audit_service=audit_service,
        memory=memory,
        confirmation_broker=confirmation_broker,
        guard=guard,
        pipeline=pipeline,
        intel=intel,
        storage=storage,
        router=router,
        registry=registry,
        orchestrator=orchestrator,
        workspace=workspace,
        config_tool=config_tool,
        observability=observability,
    )


def sample_resources() -> Dict[str, Any]:
    """Real resource sample (psutil) for Level 3 / report metrics."""
    import psutil

    process = psutil.Process()
    return {
        "rss_bytes": process.memory_info().rss,
        "cpu_percent": process.cpu_percent(interval=None),
        "system_cpu_percent": psutil.cpu_percent(interval=None),
        "system_memory_percent": psutil.virtual_memory().percent,
    }
