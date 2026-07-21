import asyncio
from typing import Any, Dict, List, Optional
import logging

from .policy import Policy, PolicyEffect, PolicyResult
from .event_bus import EventBus
from .events import SentinelEvent
from . import event_types
from ..policies.loader import PolicyStore

logger = logging.getLogger(__name__)


class PolicyEngine:
    def __init__(self, default_effect: PolicyEffect = PolicyEffect.DENY, event_bus: Optional[EventBus] = None):
        self._policies: Dict[str, Policy] = {}
        self._permission_map: Dict[str, List[str]] = {}
        self._default_effect = default_effect
        self._event_bus = event_bus
        PolicyStore.get_instance().on_reload(self._on_policy_reload)

    def set_event_bus(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus

    def _emit(self, event_type: str, *, tool_id: str = "", session_id: str = "", request_id: str = "", status: str = "", details: Optional[Dict[str, Any]] = None) -> None:
        if self._event_bus is None:
            return
        asyncio.ensure_future(self._event_bus.emit(SentinelEvent.new(
            event_type=event_type,
            session_id=session_id or "",
            request_id=request_id or "",
            component="policy_engine",
            status=status,
            tool=tool_id,
            details=details,
        )))

    def _on_policy_reload(self) -> None:
        logger.info("Policy files changed, policies will use updated YAML config on next evaluate()")

    def register(self, policy: Policy, permissions: Optional[List[str]] = None) -> None:
        pid = policy.policy_id()
        if pid in self._policies:
            raise ValueError(f"Policy '{pid}' already registered")
        self._policies[pid] = policy
        for perm in permissions or []:
            self._permission_map.setdefault(perm, []).append(pid)
        logger.info("Policy registered: %s for permissions %s", pid, permissions or ["*"])

    def unregister(self, policy_id: str) -> None:
        if policy_id not in self._policies:
            raise KeyError(f"Policy '{policy_id}' not found")
        del self._policies[policy_id]
        for perm in list(self._permission_map.keys()):
            self._permission_map[perm] = [p for p in self._permission_map[perm] if p != policy_id]
            if not self._permission_map[perm]:
                del self._permission_map[perm]
        logger.info("Policy unregistered: %s", policy_id)

    def policies_for_permissions(self, permissions: List[str]) -> List[Policy]:
        seen: set = set()
        result: List[Policy] = []
        for perm in permissions:
            for pid in self._permission_map.get(perm, []):
                if pid not in seen:
                    seen.add(pid)
                    result.append(self._policies[pid])
        return result

    async def evaluate(
        self,
        tool_id: str,
        params: Dict[str, Any],
        context: Dict[str, Any],
        required_permissions: List[str],
    ) -> PolicyResult:
        sid = context.get("session_id", "")
        rid = context.get("execution_id", "")
        self._emit(event_types.POLICY_VALIDATING, tool_id=tool_id, session_id=sid, request_id=rid)
        policies = self.policies_for_permissions(required_permissions)
        if not policies:
            logger.warning(
                "No policies for permissions %s (tool=%s), defaulting to %s",
                required_permissions,
                tool_id,
                self._default_effect.value,
            )
            result = PolicyResult(
                effect=self._default_effect,
                policy_id="_default",
                reason=f"No policy covers permissions {required_permissions}",
                context={"tool_id": tool_id, "permissions": required_permissions},
            )
            if result.effect == PolicyEffect.DENY:
                self._emit(event_types.POLICY_DENIED, tool_id=tool_id, session_id=sid, request_id=rid, status="denied", details={"policy_id": "_default", "reason": result.reason})
            else:
                self._emit(event_types.POLICY_VALIDATED, tool_id=tool_id, session_id=sid, request_id=rid, status="completed", details={"effect": result.effect.value})
            return result

        evaluation_context = dict(context)
        evaluation_context["required_permissions"] = list(required_permissions)
        evaluated = [await policy.evaluate(tool_id, params, evaluation_context) for policy in policies]

        for result in evaluated:
            if result.effect == PolicyEffect.DENY:
                logger.info(
                    "Policy %s -> DENY for tool %s: %s",
                    result.policy_id,
                    tool_id,
                    result.reason,
                )
                self._emit(event_types.POLICY_DENIED, tool_id=tool_id, session_id=sid, request_id=rid, status="denied", details={"policy_id": result.policy_id, "reason": result.reason})
                return result

        confirm_results = [result for result in evaluated if result.effect == PolicyEffect.REQUIRE_CONFIRM]

        if confirm_results:
            combined = PolicyResult(
                effect=PolicyEffect.REQUIRE_CONFIRM,
                policy_id=",".join(r.policy_id for r in confirm_results),
                reason="; ".join(r.reason for r in confirm_results),
                context={"confirmations": [r.context for r in confirm_results]},
            )
            logger.info("Policy requires confirm for tool %s", tool_id)
            self._emit(event_types.POLICY_VALIDATED, tool_id=tool_id, session_id=sid, request_id=rid, status="completed", details={"effect": combined.effect.value})
            return combined

        logger.info("All policies ALLOW for tool %s", tool_id)
        result = PolicyResult(
            effect=PolicyEffect.ALLOW,
            policy_id="_all",
            reason="All policies allowed",
        )
        self._emit(event_types.POLICY_VALIDATED, tool_id=tool_id, session_id=sid, request_id=rid, status="completed", details={"effect": result.effect.value})
        return result
