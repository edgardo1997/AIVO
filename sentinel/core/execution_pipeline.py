"""Execution Pipeline — único punto de entrada para toda ejecución de herramientas.

Flujo:
  execute(tool_id, params, context)
       │
       ├─ ToolExecutionGuard.execute(ToolRequest)
       │    └→ ToolGateway.execute()
       │
       ├─ AuditService (siempre)
       ├─ PerformanceIntelligence (cuando está conectado)
       └─ FeedbackEngine (cuando está conectado)
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

from sentinel.core.tool_gateway import ToolGateway
from sentinel.core.tool import ToolResult
from sentinel.security.models import ExecutionGrantContext, ToolRequest

logger = logging.getLogger(__name__)


class ExecutionPipeline:
    """Único punto de entrada para toda ejecución de herramientas.

    Ningún componente puede ejecutar herramientas sin pasar por este pipeline.
    """

    def __init__(
        self,
        tool_gateway: Optional[ToolGateway] = None,
        tool_execution_guard: Optional[Any] = None,
        audit_service: Optional[Any] = None,
        performance_intelligence: Optional[Any] = None,
        feedback_engine: Optional[Any] = None,
        event_bus: Optional[Any] = None,
    ):
        self._gateway = tool_gateway
        self._guard = tool_execution_guard
        self._audit = audit_service
        self._perf_intel = performance_intelligence
        self._feedback = feedback_engine
        self._event_bus = event_bus
        self._first_action_recorder: Optional[Any] = None

        # A confirmation must ALWAYS resume through this same pipeline. Wiring
        # it here at construction closes the confirmation loop by construction:
        # any stack that pairs a real gateway with a real pipeline can never
        # leave the confirmation execution unavailable. This is the single
        # source of the "Confirmation execution pipeline is unavailable" gate.
        if self._gateway is not None and hasattr(self._gateway, "set_confirmation_executor"):

            async def _confirmation_execute(tool_id: str, params: Dict[str, Any], context: Dict[str, Any]):
                return await self.execute(tool_id, params, context, source="confirmation")

            self._gateway.set_confirmation_executor(_confirmation_execute)

    def set_first_action_recorder(self, recorder: Optional[Any]) -> None:
        """Wire a callback invoked once per session on the first successful execution."""
        self._first_action_recorder = recorder

    def set_tool_gateway(self, gateway: ToolGateway) -> None:
        self._gateway = gateway

    def set_tool_execution_guard(self, guard: Any) -> None:
        self._guard = guard

    def set_audit_service(self, service: Any) -> None:
        self._audit = service
        if self._guard is not None and hasattr(self._guard, "set_audit_service"):
            self._guard.set_audit_service(service)

    def set_consent_service(self, service: Any) -> None:
        if self._guard is not None and hasattr(self._guard, "set_consent_service"):
            self._guard.set_consent_service(service)

    def set_confirmation_broker(self, broker: Any) -> None:
        if self._guard is not None and hasattr(self._guard, "set_confirmation_broker"):
            self._guard.set_confirmation_broker(broker)
        if self._guard is not None and hasattr(self._guard, "set_execution_grant_repository"):
            self._guard.set_execution_grant_repository(getattr(broker, "_grants", None))

    def set_risk_classifier(self, classifier: Any) -> None:
        if self._guard is not None and hasattr(self._guard, "set_risk_classifier"):
            self._guard.set_risk_classifier(classifier)

    def set_performance_intelligence(self, pi: Any) -> None:
        self._perf_intel = pi

    def set_feedback_engine(self, fe: Any) -> None:
        self._feedback = fe

    async def execute(
        self,
        tool_id: str,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
        *,
        source: str = "orchestrator",
        execution_grant: Optional[ExecutionGrantContext] = None,
    ) -> ToolResult:
        """Ejecuta una herramienta a través del pipeline unificado.

        Args:
            tool_id: ID de la herramienta a ejecutar
            params: Parámetros de la herramienta
            context: Contexto de ejecución
            source: Origen de la ejecución (orchestrator, grounding, rollback, skill)

        Returns:
            ToolResult con el resultado de la ejecución
        """
        ctx: Dict[str, Any] = dict(context or {})
        if execution_grant is not None:
            ctx["execution_grant"] = execution_grant
        start = time.monotonic()

        result = await self._execute_guarded(tool_id, params, ctx, source)

        elapsed = (time.monotonic() - start) * 1000
        if result.duration_ms is None:
            result.duration_ms = elapsed

        self._record_metrics(tool_id, params, result, ctx, elapsed)
        if result.success and self._first_action_recorder is not None:
            try:
                self._first_action_recorder(tool_id=tool_id, session_id=self._extract_session_id(ctx))
            except Exception:
                logger.debug("first_action metric not recorded", exc_info=True)
        return result

    def _extract_session_id(self, context: Dict[str, Any]) -> str:
        identity = context.get("identity", {})
        session_id = ""
        if isinstance(identity, dict):
            session_id = identity.get("session_id", "")
            if not session_id and isinstance(identity.get("metadata"), dict):
                session_id = identity["metadata"].get("session_id", "")
        return session_id or context.get("session_id", "")

    async def _execute_guarded(
        self,
        tool_id: str,
        params: Dict[str, Any],
        context: Dict[str, Any],
        source: str,
    ) -> ToolResult:
        """Ejecuta a través de ToolExecutionGuard — no permite bypass."""
        if self._guard is None:
            logger.error(
                "Security violation: no ToolExecutionGuard configured for %s", tool_id
            )
            return ToolResult.fail(
                error="Execution blocked: ToolExecutionGuard is required but not configured",
                tool_id=tool_id,
            )
        return await self._execute_via_guard(tool_id, params, context, source)

    async def _execute_via_guard(
        self,
        tool_id: str,
        params: Dict[str, Any],
        context: Dict[str, Any],
        source: str,
    ) -> ToolResult:
        """Convierte la solicitud a ToolRequest y la envía a ToolExecutionGuard."""
        identity = context.get("identity", {})
        user_id = ""
        session_id = ""
        execution_id = ""
        if isinstance(identity, dict):
            user_id = identity.get("user_id", "")
            session_id = identity.get("session_id", "")
            if not session_id and isinstance(identity.get("metadata"), dict):
                session_id = identity["metadata"].get("session_id", "")
        session_id = session_id or context.get("session_id", "")
        if session_id:
            context["session_id"] = session_id
        execution_id = context.get("execution_id", "")

        request = ToolRequest(
            tool_name=tool_id,
            arguments=params,
            source=source,
            user_context=context,
            session_id=session_id,
            user_id=user_id,
            execution_id=execution_id,
        )
        try:
            guard_result = await self._guard.execute(request)
            policy_decision = guard_result.decision.value if hasattr(guard_result, "decision") else None
            if guard_result.success:
                return ToolResult(
                    success=True,
                    data=guard_result.data,
                    tool_id=tool_id,
                    policy_decision=policy_decision,
                    policy_result=getattr(guard_result, "policy_result", None),
                    quality_result=getattr(guard_result, "quality_result", None),
                    requires_confirmation=getattr(guard_result, "requires_confirmation", False),
                )
            return ToolResult(
                success=False,
                data=guard_result.data,
                error=guard_result.error or "Blocked by ToolExecutionGuard",
                tool_id=tool_id,
                policy_decision=policy_decision,
                policy_result=getattr(guard_result, "policy_result", None),
                quality_result=getattr(guard_result, "quality_result", None),
                requires_confirmation=getattr(guard_result, "requires_confirmation", False),
            )
        except Exception as e:
            logger.exception("ToolExecutionGuard failed for '%s'", tool_id)
            return ToolResult.fail(
                error=f"Security guard error: {e}",
                tool_id=tool_id,
            )

    def _record_metrics(
        self,
        tool_id: str,
        params: Dict[str, Any],
        result: ToolResult,
        context: Dict[str, Any],
        elapsed_ms: float,
    ) -> None:
        """Registra métricas de ejecución en los componentes conectados."""
        if self._audit is not None:
            try:
                identity = context.get("identity", {})
                user_id = identity.get("user_id", "") if isinstance(identity, dict) else ""
                self._audit.log_action(
                    action="tool_execution",
                    details={
                        "tool_id": result.tool_id or tool_id,
                        "source": context.get("source", ""),
                        "duration_ms": elapsed_ms,
                        "success": result.success,
                        "policy_decision": getattr(result, "policy_decision", None),
                        "error": result.error,
                    },
                    status="completed" if result.success else "failed",
                    user=user_id,
                )
            except Exception as e:
                logger.debug("Audit log failed for %s: %s", tool_id, e)

        if self._perf_intel is not None:
            try:
                metrics_cls = getattr(self._perf_intel, "_metrics_type", None)
                if metrics_cls is None:
                    from sentinel.core.performance_intelligence import ExecutionMetrics
                    metrics_cls = ExecutionMetrics
                metric = metrics_cls(
                    model_id=tool_id,
                    task_type="tool_execution",
                    intent=context.get("intent", ""),
                    latency=elapsed_ms,
                    tokens_used=0,
                    cost=0.0,
                    success=result.success,
                    error=result.error,
                )
                if hasattr(self._perf_intel, "_metrics") and hasattr(self._perf_intel._metrics, "append"):
                    self._perf_intel._metrics.append(metric)
            except Exception as e:
                logger.debug("PerformanceIntelligence record failed for %s: %s", tool_id, e)

    async def check_tool(self, tool_id: str) -> Optional[Dict[str, Any]]:
        """Verifica si una herramienta existe sin ejecutarla."""
        if self._gateway is None:
            return None
        spec = self._gateway.get_spec(tool_id)
        if spec is None:
            return None
        return {
            "id": spec.id,
            "name": spec.name,
            "status": spec.status.value,
            "timeout": spec.timeout_seconds,
        }
