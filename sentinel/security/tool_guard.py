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

import dataclasses
import logging
import json
import hmac
import hashlib
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sentinel.security.models import (
    ExecutionGrantContext,
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
        self._confirmation_broker = None
        self._decision = decision_engine
        self._risk = risk_classifier
        self._validator = argument_validator or ArgumentValidator()
        self._rate_limiter = rate_limiter or ToolRateLimiter()
        self._last_policy_result: Optional[Any] = None
        self._execution_grants: Any = None
        if self._gateway is not None and hasattr(self._gateway, "set_execution_guard"):
            self._gateway.set_execution_guard(self)

    # ── Setters (inyección post-construcción) ─────────────────

    def set_tool_gateway(self, gateway: Any) -> None:
        self._gateway = gateway
        if self._gateway is not None and hasattr(self._gateway, "set_execution_guard"):
            self._gateway.set_execution_guard(self)

    def set_policy_engine(self, engine: Any) -> None:
        self._policy = engine

    def set_audit_service(self, service: Any) -> None:
        self._audit = service

    def set_consent_service(self, service: Any) -> None:
        self._consent = service

    def set_confirmation_broker(self, broker: Any) -> None:
        """Use the shared durable broker for pending confirmations."""
        self._confirmation_broker = broker

    def set_execution_grant_repository(self, repository: Any) -> None:
        self._execution_grants = repository

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
        self._last_policy_result = None
        logger.info(
            "ToolExecutionGuard: %s from %s (user=%s, session=%s)",
            request.tool_name, request.source, request.user_id, request.session_id,
        )

        # Ambiguity check: no tool may execute with unresolved material ambiguity.
        ambiguity_denial = self._check_ambiguity(request)
        if ambiguity_denial is not None:
            await self._log_audit({
                "event": "tool_execution_ambiguity_denied",
                "tool": request.tool_name,
                "source": request.source,
                "user_id": request.user_id,
                "session_id": request.session_id,
                "execution_id": request.execution_id,
                "error": ambiguity_denial.error,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            return ambiguity_denial

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

        grant_failure = self._consume_execution_grant(request)
        if grant_failure is not None:
            return grant_failure

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
        risk_level = self._classify_risk(request, risk_level)

        # 5. Check policy
        policy_result = await self._evaluate_policy(request, risk_level)
        if policy_result.decision in (SecurityDecision.DENIED,):
            return policy_result
        # 6. Execute via ToolGateway
        result = await self._execute_via_gateway(request)
        if policy_result.user_confirmed:
            result.user_confirmed = True

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
            # A policy may inspect this context to determine whether it still
            # needs consent.  Do not expose an unverified grant as authority.
            policy_context = dict(request.user_context or {})
            if not self._is_already_approved(request):
                policy_context.pop("_confirmation_grant", None)
            policy_result = await self._policy.evaluate(
                tool_id=request.tool_name,
                params=request.arguments,
                context=policy_context,
                required_permissions=required_permissions,
            )
            self._last_policy_result = policy_result

            effect = getattr(policy_result, "effect", None)
            if effect is not None:
                effect_str = effect.value if hasattr(effect, "value") else str(effect)

                if effect_str in ("deny", "DENY"):
                    reason = getattr(policy_result, "reason", "Blocked by policy")
                    policy_id = getattr(policy_result, "policy_id", "unknown")
                    if policy_id == "identity_permissions":
                        reason = json.dumps(
                            {
                                "error_type": "AUTHENTICATION_REQUIRED",
                                "message": reason,
                                "required": ["user_id", "session_id"],
                            }
                        )
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

                    if self._is_already_approved(request):
                        return ExecutionResult(
                            success=True,
                            risk_level=risk_level,
                            decision=SecurityDecision.APPROVED,
                            policy_id=policy_id,
                            policy_reason=reason,
                            tool_name=request.tool_name,
                            user_confirmed=True,
                        )

                    action_id = self._request_confirmation(request, reason, risk_level)
                    if not action_id:
                        return ExecutionResult(
                            success=False,
                            error=f"Confirmation service unavailable: {reason}",
                            risk_level=risk_level,
                            decision=SecurityDecision.DENIED,
                            policy_id=policy_id,
                            policy_reason=reason,
                            tool_name=request.tool_name,
                        )
                    return ExecutionResult(
                        success=False,
                        data={"action_id": action_id},
                        risk_level=risk_level,
                        decision=SecurityDecision.REQUIRE_CONFIRMATION,
                        policy_id=policy_id,
                        policy_reason=reason,
                        tool_name=request.tool_name,
                        requires_confirmation=True,
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

    def _classify_risk(self, request: ToolRequest, current: RiskLevel) -> RiskLevel:
        """Clasifica el riesgo de la solicitud con el RiskClassifier del sistema.

        Construye un Intent/Plan mínimo a partir del ToolRequest para que la
        firma del RiskClassifier (intent, plan, context) sea respetada.
        """
        if self._risk is None:
            return current
        try:
            from sentinel.core.intent import Intent
            from sentinel.core.planner import Plan, PlanStep

            intent_data = request.user_context.get("intent")
            if isinstance(intent_data, Intent):
                intent = intent_data
            elif isinstance(intent_data, dict):
                intent = Intent(
                    action=intent_data.get("action", "execute"),
                    target=intent_data.get("target", request.tool_name),
                    parameters=intent_data.get("parameters") or {},
                )
            else:
                intent = Intent(
                    action="execute",
                    target=request.tool_name,
                    parameters=request.arguments,
                )
            plan = Plan(
                steps=[
                    PlanStep(
                        id="s1",
                        tool_id=request.tool_name,
                        params=request.arguments,
                        estimated_impact="medium",
                    )
                ],
                intent=intent,
            )
            risk = self._risk.classify(intent, plan, request.user_context)
            if hasattr(risk, "level"):
                return _max_risk(current, getattr(RiskLevel, risk.level.upper(), RiskLevel.LOW))
        except Exception as e:
            logger.warning("Risk classification failed: %s", e)
        return current

    def _is_already_approved(self, request: ToolRequest) -> bool:
        """Accept only the exact parameters and identity issued by the broker."""
        ctx = request.user_context or {}
        grant = ctx.get("_confirmation_grant") or {}
        if not request.session_id:
            return False
        if not request.user_id or grant.get("user_id") != request.user_id or grant.get("tool_id") != request.tool_name:
            return False
        expected_params_hash = self._confirmation_hash(request.arguments)
        if not grant.get("params_hash") or not hmac.compare_digest(grant["params_hash"], expected_params_hash):
            return False
        identity = ctx.get("identity") or {}
        expected_identity_hash = self._confirmation_hash({
            "user_id": request.user_id,
            "session_id": identity.get("session_id", ""),
        })
        return bool(grant.get("identity_hash")) and hmac.compare_digest(
            grant["identity_hash"], expected_identity_hash
        )

    def _check_ambiguity(self, request: ToolRequest) -> Optional[ExecutionResult]:
        """Deny execution when material ambiguity remains unresolved."""
        ctx = request.user_context or {}
        ambiguity = ctx.get("ambiguity_decision")
        understanding = ctx.get("input_understanding")

        def _extract(field: str, default=None):
            if isinstance(ambiguity, dict):
                return ambiguity.get(field, default)
            if dataclasses.is_dataclass(ambiguity):
                return getattr(ambiguity, field, default)
            return default

        if ambiguity is not None:
            if _extract("requires_clarification") is True:
                return ExecutionResult(
                    success=False,
                    error="AMBIGUITY_UNRESOLVED: clarification required",
                    risk_level=RiskLevel.MEDIUM,
                    decision=SecurityDecision.DENIED,
                    tool_name=request.tool_name,
                )

            ask_clarification = _extract("ask_clarification")
            if ask_clarification is True:
                return ExecutionResult(
                    success=False,
                    error="AMBIGUITY_UNRESOLVED: ask_clarification set",
                    risk_level=RiskLevel.MEDIUM,
                    decision=SecurityDecision.DENIED,
                    tool_name=request.tool_name,
                )

            level = _extract("ambiguity_level") or ""
            if isinstance(level, str) and level.lower() in ("material", "high"):
                return ExecutionResult(
                    success=False,
                    error="AMBIGUITY_UNRESOLVED: material ambiguity",
                    risk_level=RiskLevel.HIGH,
                    decision=SecurityDecision.DENIED,
                    tool_name=request.tool_name,
                )

            action = _extract("action")
            if action == "reject":
                return ExecutionResult(
                    success=False,
                    error="AMBIGUITY_UNRESOLVED: rejected by ambiguity engine",
                    risk_level=RiskLevel.HIGH,
                    decision=SecurityDecision.DENIED,
                    tool_name=request.tool_name,
                )

            decision_id = _extract("decision_id") or _extract("id")
            grant_obj = ctx.get("execution_grant")
            grant_id = None
            if dataclasses.is_dataclass(grant_obj):
                grant_id = getattr(grant_obj, "ambiguity_decision_id", None)
            elif isinstance(grant_obj, dict):
                grant_id = grant_obj.get("ambiguity_decision_id")
            if decision_id is not None and grant_id is not None and decision_id != grant_id:
                return ExecutionResult(
                    success=False,
                    error="AMBIGUITY_UNRESOLVED: ambiguity decision mismatch",
                    risk_level=RiskLevel.HIGH,
                    decision=SecurityDecision.DENIED,
                    tool_name=request.tool_name,
                )

        if understanding is not None:
            def _u(field: str, default=None):
                if isinstance(understanding, dict):
                    return understanding.get(field, default)
                if dataclasses.is_dataclass(understanding):
                    return getattr(understanding, field, default)
                return default

            selected_intent = _u("selected_intent")
            if selected_intent == "informational":
                return ExecutionResult(
                    success=False,
                    error="AMBIGUITY_UNRESOLVED: informational intent cannot execute",
                    risk_level=RiskLevel.LOW,
                    decision=SecurityDecision.DENIED,
                    tool_name=request.tool_name,
                )

            if _u("requires_clarification") is True or _u("ambiguity_level") in ("material", "high"):
                return ExecutionResult(
                    success=False,
                    error="AMBIGUITY_UNRESOLVED: input requires clarification",
                    risk_level=RiskLevel.MEDIUM,
                    decision=SecurityDecision.DENIED,
                    tool_name=request.tool_name,
                )

            # Target-dependent tools require an exact selected target, either
            # from entity resolution or from the tool arguments themselves.
            target = _u("selected_target")
            args = request.arguments or {}
            explicit_target = (
                args.get("path") or args.get("target") or args.get("file")
                or args.get("app") or args.get("contact")
            )
            target_required = any(k in args for k in ("path", "target", "file", "app", "contact"))
            if target_required and not (target or explicit_target):
                return ExecutionResult(
                    success=False,
                    error="AMBIGUITY_UNRESOLVED: exact target missing",
                    risk_level=RiskLevel.MEDIUM,
                    decision=SecurityDecision.DENIED,
                    tool_name=request.tool_name,
                )

            decision_id = _u("decision_id") or _u("id")
            grant_obj = ctx.get("execution_grant")
            grant_id = None
            if dataclasses.is_dataclass(grant_obj):
                grant_id = getattr(grant_obj, "input_understanding_id", None)
            elif isinstance(grant_obj, dict):
                grant_id = grant_obj.get("input_understanding_id")
            if decision_id is not None and grant_id is not None and decision_id != grant_id:
                return ExecutionResult(
                    success=False,
                    error="AMBIGUITY_UNRESOLVED: input understanding mismatch",
                    risk_level=RiskLevel.HIGH,
                    decision=SecurityDecision.DENIED,
                    tool_name=request.tool_name,
                )

        return None

    def _consume_execution_grant(self, request: ToolRequest) -> Optional[ExecutionResult]:
        raw_grant = (request.user_context or {}).get("execution_grant")
        if raw_grant is None and request.source != "approved_plan":
            return None
        if not isinstance(raw_grant, ExecutionGrantContext):
            return ExecutionResult(success=False, error="ExecutionGrantContext is required for approved plan execution", decision=SecurityDecision.DENIED, tool_name=request.tool_name)
        grant = raw_grant
        identity = (request.user_context or {}).get("identity") or {}
        identity_hash = self._confirmation_hash({"user_id": request.user_id, "session_id": request.session_id})
        params_hash = self._confirmation_hash({"tool_id": request.tool_name, "params": request.arguments, "plan_id": grant.plan_id, "identity_hash": identity_hash})
        if (not request.user_id or not request.session_id or grant.user_id != request.user_id or grant.session_id != request.session_id or grant.tool_id != request.tool_name or grant.identity_hash != identity_hash or grant.params_hash != params_hash or identity.get("user_id") != request.user_id or identity.get("session_id") != request.session_id or self._execution_grants is None):
            return ExecutionResult(success=False, error="Execution grant binding mismatch", decision=SecurityDecision.DENIED, tool_name=request.tool_name)
        binding = {"plan_grant_id": grant.plan_grant_id, "plan_id": grant.plan_id, "plan_hash": grant.plan_hash, "step_id": grant.step_id, "step_index": grant.step_index, "tool_id": grant.tool_id, "params_hash": grant.params_hash, "identity_hash": grant.identity_hash, "session_id": grant.session_id}
        try:
            consumed = self._execution_grants.consume_step(grant.step_grant_id, binding)
        except Exception:
            logger.exception("Durable execution grant validation failed")
            consumed = False
        if not consumed:
            return ExecutionResult(success=False, error="Execution grant rejected, expired, or already consumed", decision=SecurityDecision.DENIED, tool_name=request.tool_name)
        request.user_context["validated_execution_grant"] = grant
        return None

    @staticmethod
    def _confirmation_hash(value: Any) -> str:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def _request_confirmation(
        self, request: ToolRequest, reason: str, risk_level: RiskLevel
    ) -> Optional[str]:
        if self._confirmation_broker is None:
            return None
        if not request.user_id or not request.session_id:
            logger.warning("Confirmation rejected: authenticated user and non-empty session are required")
            return None
        try:
            return self._confirmation_broker.request(
                tool_id=request.tool_name,
                params=request.arguments,
                context=request.user_context,
                reason=f"Execute {request.tool_name}: {reason}",
                risk_level=risk_level.value,
                plan_id=str(request.user_context.get("plan_id", "")),
            )
        except Exception as e:
            logger.warning("Confirmation request failed: %s", e)
            return None

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
            context["issuing_guard"] = self
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
                policy_result=getattr(result, "policy_result", None),
                quality_result=getattr(result, "quality_result", None),
                requires_confirmation=getattr(result, "requires_confirmation", False),
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
                entry.get("event", "tool_execution"),
                entry,
                entry.get("decision", ""),
                entry.get("user_id", "system"),
            )
        except Exception as e:
            logger.warning("Audit log failed: %s", e)
