"""ToolExecutionGuard — único punto autorizado para ejecutar herramientas.

Flujo interno obligatorio:
  1. validate_request()    — argumentos válidos yseguros
  2. check_rate_limit()    — control de frecuencia
  3. check_tool_exists()   — herramienta registrada y habilitada
  4. calculate_risk()      — nivel deriesgo
  5. check_permissions()   — PolicyEngine
  6. handle_confirmation() — ConsentService si requiere confirmación
  7. execute()             — ToolGateway (único gateway)
  8. audit()               — registro obligatorio
  9. return result
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sentinel.security.models import (
    ToolRequest,
    ExecutionResult,
    RiskLevel,
    SecurityDecision,
)
from sentinel.security.argument_validator import ArgumentValidator, _max_risk
from sentinel.security.tool_rate_limiter import ToolRateLimiter

logger = logging.getLogger(__name__)


class ToolExecutionGuard:
    """Único punto autorizado para ejecutar herramientas.

    Ningún modelo, agente, workflow o componente interno puede ejecutar
    acciones del sistema sin atravesar este guard.
    """

    def __init__(
        self,
        tool_gateway: Any = None,
        policy_engine: Any = None,
        audit_service: Any = None,
        consent_service: Any = None,
        argument_validator: Optional[ArgumentValidator] = None,
        rate_limiter: Optional[ToolRateLimiter] = None,
        decision_engine: Any = None,
        risk_classifier: Any = None,
    ):
        self._gateway = tool_gateway
        self._policy = policy_engine
        self._audit = audit_service
        self._consent = consent_service
        self._decision = decision_engine
        self._risk = risk_classifier
        self._validator = argument_validator or ArgumentValidator()
        self._rate_limiter = rate_limiter or ToolRateLimiter()

    # ── Setters (inyección post-construcción) ─────────────────

    def set_tool_gateway(self, gateway: Any) -> None:
        self._gateway = gateway

    def set_policy_engine(self, engine: Any) -> None:
        self._policy = engine

    def set_audit_service(self, service: Any) -> None:
        self._audit = service

    def set_consent_service(self, service: Any) -> None:
        self._consent = service

    def set_decision_engine(self, engine: Any) -> None:
        self._decision = engine

    def set_risk_classifier(self, classifier: Any) -> None:
        self._risk = classifier

    # ── Execute (método principal) ───────────────────────────

    async def execute(self, request: ToolRequest) -> ExecutionResult:
        """Ejecuta una herramienta con todas las comprobaciones de seguridad.

        Este es el ÚNICO método que debe llamar a ToolGateway.execute().
        """
        start = time.monotonic()
        logger.info(
            "ToolExecutionGuard: %s from %s (user=%s, session=%s)",
            request.tool_name, request.source, request.user_id, request.session_id,
        )

        # 1. Validate request format
        validation = self._validator.validate(request.tool_name, request.arguments)
        if not validation.valid:
            return ExecutionResult(
                success=False,
                error=f"Argument validation failed: {'; '.join(validation.errors)}",
                risk_level=validation.risk_level,
                decision=SecurityDecision.DENIED,
                tool_name=request.tool_name,
            )

        risk_level = validation.risk_level

        # 2. Check rate limit
        rate_result = self._rate_limiter.check(request.tool_name)
        if rate_result.blocked:
            return ExecutionResult(
                success=False,
                error=rate_result.reason,
                risk_level=RiskLevel.MEDIUM,
                decision=SecurityDecision.DENIED,
                tool_name=request.tool_name,
            )

        # 3. Check tool exists
        if self._gateway:
            spec = self._gateway.get_spec(request.tool_name)
            if spec is None:
                return ExecutionResult(
                    success=False,
                    error=f"Tool '{request.tool_name}' not found",
                    risk_level=RiskLevel.LOW,
                    decision=SecurityDecision.DENIED,
                    tool_name=request.tool_name,
                )

        # 4. Calculate risk
        if self._risk and request.user_context.get("intent"):
            try:
                risk = self._risk.classify(
                    request.user_context.get("intent"),
                    request.tool_name,
                    request.arguments,
                )
                if hasattr(risk, "level"):
                    risk_level = _max_risk(risk_level, getattr(RiskLevel, risk.level.upper(), RiskLevel.LOW))
            except Exception as e:
                logger.warning("Risk classification failed: %s", e)

        # 5. Check policy
        policy_result = await self._evaluate_policy(request, risk_level)
        if policy_result.decision in (SecurityDecision.DENIED,):
            return policy_result
        if policy_result.decision == SecurityDecision.REQUIRE_CONFIRMATION:
            return policy_result

        # 6. Execute via ToolGateway
        result = await self._execute_via_gateway(request)

        # 7. Audit
        audit_entry = self._build_audit_entry(request, result, risk_level, SecurityDecision.APPROVED)
        result.audit_entry = audit_entry
        await self._log_audit(audit_entry)

        result.duration_ms = (time.monotonic() - start) * 1000
        return result

    async def _evaluate_policy(
        self, request: ToolRequest, risk_level: RiskLevel
    ) -> ExecutionResult:
        if self._policy is None:
            return ExecutionResult(
                success=True,
                risk_level=risk_level,
                decision=SecurityDecision.APPROVED,
                tool_name=request.tool_name,
            )

        try:
            required_permissions: list = []
            if self._gateway:
                spec = self._gateway.get_spec(request.tool_name)
                if spec and hasattr(spec, "required_permissions"):
                    required_permissions = list(spec.required_permissions)
            policy_result = await self._policy.evaluate(
                tool_id=request.tool_name,
                params=request.arguments,
                context=request.user_context,
                required_permissions=required_permissions,
            )

            effect = getattr(policy_result, "effect", None)
            if effect is not None:
                effect_str = effect.value if hasattr(effect, "value") else str(effect)

                if effect_str in ("deny", "DENY"):
                    reason = getattr(policy_result, "reason", "Blocked by policy")
                    policy_id = getattr(policy_result, "policy_id", "unknown")
                    return ExecutionResult(
                        success=False,
                        error=reason,
                        risk_level=risk_level,
                        decision=SecurityDecision.DENIED,
                        policy_id=policy_id,
                        policy_reason=reason,
                        tool_name=request.tool_name,
                    )

                if effect_str in ("require_confirm", "REQUIRE_CONFIRM"):
                    reason = getattr(policy_result, "reason", "Requires confirmation")
                    policy_id = getattr(policy_result, "policy_id", "unknown")

                    confirmed = await self._request_confirmation(request, reason, risk_level)
                    if not confirmed:
                        return ExecutionResult(
                            success=False,
                            error=f"Confirmation denied: {reason}",
                            risk_level=risk_level,
                            decision=SecurityDecision.DENIED,
                            policy_id=policy_id,
                            policy_reason=reason,
                            tool_name=request.tool_name,
                            user_confirmed=False,
                        )
                    return ExecutionResult(
                        success=True,
                        risk_level=risk_level,
                        decision=SecurityDecision.APPROVED,
                        policy_id=policy_id,
                        policy_reason=reason,
                        tool_name=request.tool_name,
                        user_confirmed=True,
                    )
        except Exception as e:
            logger.error("Policy evaluation failed for %s: %s", request.tool_name, e)
            return ExecutionResult(
                success=False,
                error=f"Policy evaluation error: {e}",
                risk_level=RiskLevel.HIGH,
                decision=SecurityDecision.DENIED,
                tool_name=request.tool_name,
            )

        return ExecutionResult(
            success=True,
            risk_level=risk_level,
            decision=SecurityDecision.APPROVED,
            tool_name=request.tool_name,
        )

    async def _request_confirmation(
        self, request: ToolRequest, reason: str, risk_level: RiskLevel
    ) -> bool:
        if self._consent is None:
            return False
        try:
            result = await self._consent.request_confirmation(
                action_id=request.execution_id or request.tool_name,
                description=f"Execute {request.tool_name}: {reason}",
                risk_level=risk_level.value,
                user_id=request.user_id,
                session_id=request.session_id,
                context={
                    "tool": request.tool_name,
                    "arguments": request.arguments,
                    "source": request.source,
                },
            )
            return bool(result)
        except Exception as e:
            logger.warning("Confirmation request failed: %s", e)
            return False

    async def _execute_via_gateway(self, request: ToolRequest) -> ExecutionResult:
        if self._gateway is None:
            return ExecutionResult(
                success=False,
                error="No ToolGateway configured",
                risk_level=RiskLevel.LOW,
                decision=SecurityDecision.DENIED,
                tool_name=request.tool_name,
            )
        try:
            context = dict(request.user_context)
            context["_guard_execution"] = True
            context["execution_id"] = request.execution_id
            context["source"] = request.source

            result = await self._gateway.execute(
                request.tool_name,
                request.arguments,
                context=context,
            )
            return ExecutionResult(
                success=getattr(result, "success", True),
                data=getattr(result, "data", None),
                error=getattr(result, "error", None),
                risk_level=RiskLevel.LOW,
                decision=SecurityDecision.APPROVED,
                tool_name=request.tool_name,
            )
        except Exception as e:
            logger.exception("Gateway execution failed for '%s'", request.tool_name)
            return ExecutionResult(
                success=False,
                error=str(e),
                risk_level=RiskLevel.HIGH,
                decision=SecurityDecision.DENIED,
                tool_name=request.tool_name,
            )

    def _build_audit_entry(
        self,
        request: ToolRequest,
        result: ExecutionResult,
        risk_level: RiskLevel,
        decision: SecurityDecision,
    ) -> Dict[str, Any]:
        return {
            "event": "tool_execution",
            "tool": request.tool_name,
            "source": request.source,
            "user_id": request.user_id,
            "session_id": request.session_id,
            "execution_id": request.execution_id,
            "model_id": request.model_id,
            "provider_id": request.provider_id,
            "risk": risk_level.value,
            "decision": decision.value,
            "user_confirmation": result.user_confirmed,
            "success": result.success,
            "error": result.error,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def _log_audit(self, entry: Dict[str, Any]) -> None:
        if self._audit is None:
            logger.info("AUDIT: %s", entry)
            return
        try:
            self._audit.log_action(
                "tool_execution",
                entry,
                entry["decision"],
                entry.get("user_id", "system"),
            )
        except Exception as e:
            logger.warning("Audit log failed: %s", e)
