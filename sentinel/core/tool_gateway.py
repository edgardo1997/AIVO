import asyncio
from dataclasses import asdict
from typing import Any, Dict, List, Optional, TYPE_CHECKING
import time
import logging
import uuid

from .tool import Tool, ToolResult, ToolSpec, ToolStatus
from .policy import PolicyEffect
from .policy_engine import PolicyEngine
from .context import ContextEngine
from .quality_gate import QualityGate
from .recovery import ErrorClassifier

if TYPE_CHECKING:
    from .capability_registry import CapabilityRegistry

logger = logging.getLogger(__name__)


class ToolGateway:
    def __init__(
        self,
        policy_engine: Optional[PolicyEngine] = None,
        context_engine: Optional[ContextEngine] = None,
        quality_gate: Optional[QualityGate] = None,
    ):
        self._tools: Dict[str, Tool] = {}
        self._policy_engine = policy_engine
        self._context_engine = context_engine
        self._quality_gate = quality_gate or QualityGate()
        self._capability_registry: Any = None
        self._audit_service: Any = None
        self._agent_registry: Any = None
        self._trigger_engine: Any = None
        self._hardening: Any = None
        self._confirmation_broker: Any = None
        self._observability: Any = None

    def set_hardening(self, hardening: Any) -> None:
        self._hardening = hardening

    def set_confirmation_broker(self, broker: Any) -> None:
        self._confirmation_broker = broker

    def set_observability(self, service: Any) -> None:
        self._observability = service

    async def confirm(self, action_id: str, approved: bool, identity: Dict[str, Any]) -> ToolResult:
        if self._confirmation_broker is None:
            return ToolResult.fail("Confirmation service is unavailable")
        try:
            grant = self._confirmation_broker.consume(action_id, identity.get("user_id", ""), approved)
        except PermissionError as exc:
            if self._audit_service:
                self._audit_service.log_action(
                    "confirmation_denied", action_id, "denied", identity.get("user_id", "unknown")
                )
            return ToolResult.fail(str(exc))
        if grant is None:
            if self._audit_service:
                self._audit_service.log_action(
                    "confirmation_rejected_or_expired", action_id, "denied", identity.get("user_id", "unknown")
                )
            return ToolResult.fail("Confirmation expired, rejected, or already consumed")
        if self._audit_service:
            self._audit_service.log_action(
                "confirmation_approved", f"{action_id}:{grant.tool_id}", "authorized", grant.user_id
            )
        context = dict(grant.context)
        context["identity"] = identity
        context["_confirmation_grant"] = {"action_id": action_id, "tool_id": grant.tool_id, "user_id": grant.user_id}
        return await self.execute(grant.tool_id, grant.params, context)

    def set_policy_engine(self, engine: PolicyEngine) -> None:
        self._policy_engine = engine

    def set_context_engine(self, engine: ContextEngine) -> None:
        self._context_engine = engine

    def set_capability_registry(self, registry: "CapabilityRegistry") -> None:
        self._capability_registry = registry

    def set_audit_service(self, service: Any) -> None:
        self._audit_service = service

    def set_agent_registry(self, registry: Any) -> None:
        self._agent_registry = registry

    def set_trigger_engine(self, engine: Any) -> None:
        self._trigger_engine = engine

    def register(self, tool: Tool) -> None:
        spec = tool.spec()
        if spec.status == ToolStatus.ACTIVE and not spec.required_permissions:
            raise ValueError(f"Active tool '{spec.id}' must declare at least one required permission")
        if spec.id in self._tools:
            raise ValueError(f"Tool '{spec.id}' already registered")
        self._tools[spec.id] = tool
        if self._capability_registry is not None:
            self._register_capability(spec)
        logger.info("Tool registered: %s v%s", spec.id, spec.version)

    def _register_capability(self, spec: ToolSpec) -> None:
        from .capability_registry import capability_from_spec

        cap = capability_from_spec(
            spec_id=spec.id,
            name=spec.name,
            description=spec.description,
            version=spec.version,
            parameters=spec.parameters,
            permissions=spec.required_permissions,
            timeout_seconds=spec.timeout_seconds,
            category=spec.category,
        )
        self._capability_registry.register(cap)

    def unregister(self, tool_id: str) -> None:
        if tool_id not in self._tools:
            raise KeyError(f"Tool '{tool_id}' not found")
        del self._tools[tool_id]
        logger.info("Tool unregistered: %s", tool_id)

    def get_spec(self, tool_id: str) -> Optional[ToolSpec]:
        tool = self._tools.get(tool_id)
        return tool.spec() if tool else None

    def list_specs(self) -> List[ToolSpec]:
        return [t.spec() for t in self._tools.values()]

    def list_active(self) -> List[ToolSpec]:
        return [t.spec() for t in self._tools.values() if t.spec().status == ToolStatus.ACTIVE]

    async def execute(
        self,
        tool_id: str,
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> ToolResult:
        ctx: Dict[str, Any] = dict(context or {})
        identity = ctx.get("identity")
        if hasattr(identity, "to_dict"):
            identity = identity.to_dict()
            ctx["identity"] = identity
        if not isinstance(identity, dict) or not identity.get("is_authenticated") or not identity.get("user_id"):
            result = ToolResult.fail(
                error="Identity required: authenticated user_id is missing",
                tool_id=tool_id,
            )
            result.policy_decision = "identity"
            result.policy_result = {
                "effect": "deny",
                "policy_id": "identity",
                "reason": result.error,
            }
            return result

        tool = self._tools.get(tool_id)
        if not tool:
            return ToolResult.fail(error=f"Tool '{tool_id}' not found", tool_id=tool_id)

        spec = tool.spec()
        if spec.status == ToolStatus.DISABLED:
            return ToolResult.fail(error=f"Tool '{tool_id}' is disabled", tool_id=tool_id)

        if self._context_engine and "system" not in ctx:
            try:
                sys_ctx = await self._context_engine.collect(include_processes=False)
                ctx["system"] = sys_ctx.to_dict()
                ctx["system_summary"] = sys_ctx.summary()
            except Exception as e:
                logger.warning("ContextEngine enrich failed: %s", e)

        if self._capability_registry is not None:
            ctx["_capability_registry"] = self._capability_registry

        if self._agent_registry is not None:
            ctx["_agent_registry"] = self._agent_registry

        if self._trigger_engine is not None:
            ctx["_trigger_engine"] = self._trigger_engine

        if spec.required_permissions and not self._policy_engine:
            result = ToolResult.fail(
                error=f"Blocked: no PolicyEngine configured for protected tool '{tool_id}'",
                tool_id=tool_id,
            )
            result.policy_decision = "_missing_policy_engine"
            result.policy_result = {
                "effect": "deny",
                "policy_id": "_missing_policy_engine",
                "reason": result.error,
            }
            return result

        policy_data = None
        if self._policy_engine and spec.required_permissions:
            policy_result = await self._policy_engine.evaluate(
                tool_id=tool_id,
                params=params,
                context=ctx,
                required_permissions=spec.required_permissions,
            )
            policy_data = {
                **asdict(policy_result),
                "effect": policy_result.effect.value,
            }

            if policy_result.effect == PolicyEffect.DENY:
                result = ToolResult.fail(
                    error=f"Blocked by policy '{policy_result.policy_id}': {policy_result.reason}",
                    tool_id=tool_id,
                )
                result.policy_decision = policy_result.policy_id
                result.policy_result = policy_data
                return result

            if policy_result.effect == PolicyEffect.REQUIRE_CONFIRM:
                action_id = None
                if self._confirmation_broker is not None:
                    action_id = self._confirmation_broker.request(tool_id, params, ctx, policy_result.reason)
                if self._audit_service:
                    self._audit_service.log_action(
                        "confirmation_pending",
                        f"{action_id}:{tool_id}",
                        "pending_confirmation",
                        identity.get("user_id", "unknown"),
                    )
                result = ToolResult.needs_confirm(
                    reason=policy_result.reason,
                    tool_id=tool_id,
                    policy_id=policy_result.policy_id,
                )
                result.policy_result = policy_data
                result.data = {"action_id": action_id} if action_id else None
                return result

        if spec.required_permissions:
            if self._audit_service is None:
                result = ToolResult.fail(
                    error=f"Blocked: audit service unavailable for protected tool '{tool_id}'",
                    tool_id=tool_id,
                )
                result.policy_decision = "_missing_audit_service"
                result.policy_result = policy_data
                return result
            try:
                self._audit_service.log_gateway_authorization(
                    execution_id=ctx.get("execution_id") or uuid.uuid4().hex[:12],
                    identity=identity,
                    decision=ctx.get("decision"),
                    policy=policy_data,
                    tool_id=tool_id,
                    params=params,
                )
            except Exception as exc:
                logger.error("Audit preflight failed for %s: %s", tool_id, exc)
                result = ToolResult.fail(
                    error=f"Blocked: audit preflight failed for '{tool_id}'",
                    tool_id=tool_id,
                )
                result.policy_decision = "_audit_preflight_failed"
                result.policy_result = policy_data
                return result

        span_id = (
            self._observability.start(
                tool_id,
                ctx.get("execution_id", ""),
                ctx.get("parent_span_id", ""),
            )
            if self._observability is not None
            else None
        )

        if self._hardening is not None:
            cb = self._hardening.circuit_breaker
            if not cb.allow_request(tool_id):
                self._hardening.record_circuit_block()
                if span_id:
                    self._observability.finish(span_id, False, "circuit_open")
                return ToolResult.fail(
                    error=f"Tool '{tool_id}' is circuit-open (too many recent failures)",
                    tool_id=tool_id,
                )

        start = time.monotonic()
        try:
            timeout = (
                spec.timeout_seconds or self._hardening.config.get_timeout(tool_id)
                if self._hardening
                else spec.timeout_seconds or 30
            )
            result = await asyncio.wait_for(tool.execute(params, ctx), timeout=timeout)
            elapsed = (time.monotonic() - start) * 1000
            result.tool_id = tool_id
            result.duration_ms = elapsed
            result.policy_result = policy_data
            if self._hardening is not None:
                if result.success:
                    self._hardening.circuit_breaker.record_success(tool_id)
                else:
                    category = self._hardening.classify_failure(result.error or "", tool_id)
                    if self._hardening.should_trip_circuit(category):
                        self._hardening.circuit_breaker.record_failure(tool_id)

            logger.info(
                "Tool %s finished in %.0fms (success=%s)",
                tool_id,
                elapsed,
                result.success,
            )
            quality = self._quality_gate.scan(result)
            quality_data = asdict(quality)
            if not quality.passed:
                logger.warning("QualityGate blocked output for %s: %s", tool_id, quality.issues)
                blocked = ToolResult.fail(
                    error=f"Output blocked by quality gate: {'; '.join(quality.issues)}",
                    tool_id=tool_id,
                    duration_ms=elapsed,
                )
                blocked.policy_result = policy_data
                blocked.quality_result = quality_data
                if span_id:
                    self._observability.finish(span_id, False, "quality", quality_data, blocked.policy_decision)
                return blocked
            if quality.redacted:
                logger.info("QualityGate redacted output for %s", tool_id)
                result.data = quality.redacted_data
            result.quality_result = quality_data
            if span_id:
                category = None
                if not result.success and self._hardening is not None:
                    category = ErrorClassifier.classify(result.error or "", tool_id).value
                self._observability.finish(span_id, result.success, category, quality_data, result.policy_decision)
            return result
        except asyncio.TimeoutError:
            elapsed = (time.monotonic() - start) * 1000
            logger.error("Tool %s timed out after %.0fms", tool_id, elapsed)
            if self._hardening is not None:
                self._hardening.circuit_breaker.record_failure(tool_id)
                self._hardening.classify_failure(f"timeout after {elapsed:.0f}ms", tool_id)
                self._hardening.record_timeout()
            if span_id:
                self._observability.finish(span_id, False, "transient")
            return ToolResult.fail(
                error=f"Tool '{tool_id}' timed out after {elapsed:.0f}ms",
                tool_id=tool_id,
                duration_ms=elapsed,
            )
        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            logger.error("Tool %s failed after %.0fms: %s", tool_id, elapsed, str(e))
            if self._hardening is not None:
                category = self._hardening.classify_failure(str(e), tool_id)
                if self._hardening.should_trip_circuit(category):
                    self._hardening.circuit_breaker.record_failure(tool_id)
            if span_id:
                self._observability.finish(span_id, False, category.value if self._hardening is not None else "fatal")
            return ToolResult.fail(
                error=f"Execution error: {e}",
                tool_id=tool_id,
                duration_ms=elapsed,
            )
