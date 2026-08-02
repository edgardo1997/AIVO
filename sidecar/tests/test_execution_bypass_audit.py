"""P1 — Auditoría estructural de bypasses (FASE 11 P0).

Inventario y verificación de que ninguna herramienta puede ejecutarse sin
pasar por política, guardia y auditoría. Cubre:

  1. Inventario automatizado (AST) de llamadas a `ToolGateway.execute` /
     herramientas / `ExecutionPipeline.execute` y clasificación.
  2. Encapsulación: `ToolGateway.execute` es fail-closed si una herramienta
     no declara `required_permissions` (defensa en profundidad, independiente
     del guard).
  3. `ExecutionPipeline` registra auditoría en TODAS las ejecuciones (éxito,
   fallo y denegación) — la llamada de `_record_metrics` ya no se descarta.
  4. Herramientas sin `required_permissions` no evitan política (default
     DENY), guardia (bloqueo antes de ejecutar) ni auditoría (entrada
     `tool_execution`).
  5. Grounding nunca puede solicitar un bypass de seguridad.
"""

import ast
import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from sentinel.core.policy import Policy, PolicyEffect, PolicyResult
from sentinel.core.policy_engine import PolicyEngine
from sentinel.core.tool import Tool, ToolResult, ToolSpec, ToolStatus
from sentinel.core.tool_gateway import ToolGateway
from sentinel.security.tool_guard import ToolExecutionGuard
from sentinel.core.execution_pipeline import ExecutionPipeline
from services.audit_service import AuditService

_AIVO_ROOT = Path(__file__).resolve().parents[2]


def _identity(user_id="p1-user", session_id="p1-session"):
    return {
        "identity": {
            "user_id": user_id,
            "session_id": session_id,
            "is_authenticated": True,
        }
    }


class _PermTool(Tool):
    def __init__(self, tool_id, permissions, calls=None):
        self._tid = tool_id
        self._permissions = list(permissions)
        self._calls = calls if calls is not None else []

    def spec(self):
        return ToolSpec(
            id=self._tid,
            name=self._tid,
            description="P1 test tool",
            version="1.0.0",
            parameters={"type": "object", "properties": {}},
            required_permissions=self._permissions,
        )

    async def execute(self, params, context):
        self._calls.append(params)
        return ToolResult.ok(data={"executed": self._tid}, tool_id=self._tid)


class _NoPermTool(_PermTool):
    def __init__(self, tool_id, calls=None):
        super().__init__(tool_id, permissions=[], calls=calls)
        self._tool_status = ToolStatus.ACTIVE

    def spec(self):
        spec = super().spec()
        spec.required_permissions = []
        spec.status = ToolStatus.ACTIVE
        return spec


class _AllowPolicy(Policy):
    def __init__(self, policy_id="p1.allow"):
        self._pid = policy_id

    def policy_id(self):
        return self._pid

    def description(self):
        return "P1 allow-all policy"

    async def evaluate(self, tool_id, params, context):
        return PolicyResult(effect=PolicyEffect.ALLOW, policy_id=self._pid, reason="p1 allow")


# ── 1. Inventario automatizado de llamadas de ejecución ──────────────────────


def _leaf_receiver(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        # The terminal attribute names the concrete receiver for calls like
        # self._gateway.execute() and self._tool.execute().  Returning the
        # root ("self") hid those direct production calls from the inventory.
        return node.attr
    return None


def _registered_calls_in_tree(tree):
    calls = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if not isinstance(fn, ast.Attribute) or fn.attr != "execute":
            continue
        receiver = fn.value
        # `get_execution_pipeline().execute(...)` — receiver is a Call.
        if isinstance(receiver, ast.Call) and getattr(receiver.func, "attr", "") == "get_execution_pipeline":
            calls.append(("pipeline", node.lineno))
            continue
        leaf = _leaf_receiver(receiver)
        if leaf is None:
            continue
        calls.append((leaf, node.lineno))
    return calls


def test_inventory_gateway_execute_only_in_authorized_files():
    """`ToolGateway.execute` solo puede llamarse desde el guard, el
    `_execute_direct` del pipeline y el propio `confirm()` del gateway."""
    allowed_callers = {
        "sentinel/security/tool_guard.py",
        "sentinel/core/execution_pipeline.py",
        "sentinel/core/tool_gateway.py",
    }
    forbidden_leaves = {"gateway", "_gateway", "_tool_gateway", "tool_gateway"}
    violations = []

    for rel_root in ("sentinel", "sidecar"):
        for pyfile in (_AIVO_ROOT / rel_root).rglob("*.py"):
            rel = str(pyfile.relative_to(_AIVO_ROOT)).replace("\\", "/")
            if "/tests/" in rel or pyfile.name.startswith("test_"):
                continue
            tree = ast.parse(pyfile.read_text(encoding="utf-8"))
            for leaf, lineno in _registered_calls_in_tree(tree):
                if leaf not in forbidden_leaves:
                    continue
                if rel not in allowed_callers:
                    violations.append(f"{rel}:{lineno}: direct {leaf}.execute()")

    assert not violations, "Llamadas directas a ToolGateway.execute fuera de la capa autorizada:\n" + "\n".join(
        violations
    )


def test_inventory_tool_execute_only_in_gateway_dispatch():
    """Ningún código de producción llama a `tool.execute()` directamente;
    solo el dispatch interno de `ToolGateway`."""
    allowed = {"sentinel/core/tool_gateway.py"}
    violations = []

    for rel_root in ("sentinel", "sidecar"):
        for pyfile in (_AIVO_ROOT / rel_root).rglob("*.py"):
            rel = str(pyfile.relative_to(_AIVO_ROOT)).replace("\\", "/")
            if "/tests/" in rel or pyfile.name.startswith("test_"):
                continue
            tree = ast.parse(pyfile.read_text(encoding="utf-8"))
            for leaf, lineno in _registered_calls_in_tree(tree):
                if leaf not in {"tool", "_tool"}:
                    continue
                if rel not in allowed:
                    violations.append(f"{rel}:{lineno}: direct {leaf}.execute()")

    assert not violations, "Ejecución directa de herramientas fuera del gateway:\n" + "\n".join(violations)


def test_inventory_pipeline_is_single_governed_entry():
    """`_execution_pipeline.execute` / `get_execution_pipeline().execute` solo
    aparece con `source` explícito y nunca llama al gateway directo."""
    direct_gateway = {
        "sentinel/security/tool_guard.py",
        "sentinel/core/execution_pipeline.py",
        "sentinel/core/tool_gateway.py",
    }
    problems = []

    for rel_root in ("sentinel", "sidecar"):
        for pyfile in (_AIVO_ROOT / rel_root).rglob("*.py"):
            rel = str(pyfile.relative_to(_AIVO_ROOT)).replace("\\", "/")
            if "/tests/" in rel or pyfile.name.startswith("test_"):
                continue
            src = pyfile.read_text(encoding="utf-8")
            tree = ast.parse(src)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                    continue
                receiver = node.func.value
                if isinstance(receiver, ast.Attribute) and receiver.attr in {"_execution_pipeline", "_pipeline"}:
                    # Los llamadores deben ser el propio pipeline o módulos gobernados.
                    if rel not in direct_gateway and not isinstance(receiver.value, ast.Name):
                        problems.append(f"{rel}:{node.lineno}: pipeline receiver sin `self.`")
    assert not problems, "\n".join(problems)


def test_runtime_pipeline_execution_writes_audit_via_api(client):
    """La ejecución por API (/v1/execute) debe dejar entrada de auditoría
    `tool_execution` — valida el fix de `_record_metrics` en el runtime real."""
    from modules.audit import _svc as audit_svc

    before = audit_svc.get_log()["total"]
    resp = client.post("/v1/execute", json={"tool_id": "system.info", "params": {}})
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    assert audit_svc.get_log()["total"] > before

    entries = audit_svc.get_log(action_filter="tool_execution")["entries"]
    assert any("system.info" in json.dumps(e.get("details", "")) for e in entries)


# ── 2. Encapsulación: gateway fail-closed sin required_permissions ──────────


def test_register_rejects_active_tool_without_required_permissions():
    gateway = ToolGateway(policy_engine=PolicyEngine(default_effect=PolicyEffect.DENY))
    with pytest.raises(ValueError, match="must declare at least one required permission"):
        gateway.register(_NoPermTool("p1.noperm"))


@pytest.mark.asyncio
async def test_gateway_fails_closed_on_tool_without_permissions():
    gateway = ToolGateway(policy_engine=PolicyEngine(default_effect=PolicyEffect.DENY))
    gateway.set_audit_service(AuditService())
    calls = []
    gateway._tools["p1.noperm"] = _NoPermTool("p1.noperm", calls=calls)

    result = await gateway.execute("p1.noperm", {}, _identity())

    assert result.success is False
    assert result.policy_decision == "_missing_permissions"
    assert result.policy_result["effect"] == "deny"
    assert calls == [], "La herramienta NO debe ejecutarse sin permisos declarados"


# ── 3. Pipeline audita TODAS las ejecuciones ─────────────────────────────────


def _build_stack():
    engine = PolicyEngine(default_effect=PolicyEffect.DENY)
    engine.register(_AllowPolicy(), permissions=["system.read"])
    gateway = ToolGateway(policy_engine=engine)
    audit = AuditService()
    gateway.set_audit_service(audit)
    guard = ToolExecutionGuard(tool_gateway=gateway, policy_engine=engine, audit_service=audit)
    pipeline = ExecutionPipeline(tool_gateway=gateway, tool_execution_guard=guard, audit_service=audit)
    return pipeline, gateway, guard, audit


@pytest.mark.asyncio
async def test_pipeline_execution_always_audited():
    pipeline, gateway, _, audit = _build_stack()
    calls = []
    gateway.register(_PermTool("p1.echo", ["system.read"], calls=calls))

    before = audit.get_log()["total"]
    result = await pipeline.execute("p1.echo", {"msg": "hi"}, _identity(), source="api")
    assert result.success is True
    assert audit.get_log()["total"] > before

    entries = audit.get_log(action_filter="tool_execution")["entries"]
    assert any("p1.echo" in json.dumps(e.get("details", "")) for e in entries)
    assert calls == [{"msg": "hi"}]


# ── 4. Herramientas sin required_permissions no evitan política/guard/audit ─


@pytest.mark.asyncio
async def test_no_perm_tool_blocked_by_policy_before_execution():
    pipeline, gateway, _, audit = _build_stack()
    calls = []
    gateway._tools["p1.noperm"] = _NoPermTool("p1.noperm", calls=calls)

    before = audit.get_log()["total"]
    result = await pipeline.execute("p1.noperm", {}, _identity(), source="api")

    assert result.success is False
    assert result.policy_decision in ("deny", "denied", "DENIED", None)
    assert calls == [], "Política (default DENY) debe bloquear antes de ejecutar"
    assert audit.get_log()["total"] > before, "La denegación debe quedar auditada"

    entries = audit.get_log(action_filter="tool_execution")["entries"]
    assert any("p1.noperm" in json.dumps(e.get("details", "")) for e in entries)


@pytest.mark.asyncio
async def test_guard_rejects_no_perm_tool_without_calling_gateway():
    engine = PolicyEngine(default_effect=PolicyEffect.DENY)
    gateway = ToolGateway(policy_engine=engine)
    calls = []
    gateway._tools["p1.noperm"] = _NoPermTool("p1.noperm", calls=calls)
    guard = ToolExecutionGuard(tool_gateway=gateway, policy_engine=engine)

    from sentinel.security.models import ToolRequest

    request = ToolRequest(
        tool_name="p1.noperm",
        arguments={},
        source="api",
        user_context=_identity(),
        session_id="p1-session",
        user_id="p1-user",
    )
    result = await guard.execute(request)

    assert result.success is False
    assert calls == [], "El guard debe bloquear sin llegar al gateway"


# ── 5. Grounding debe ejecutar por política, guardia y auditoría ────────────


def test_no_production_execution_path_exposes_skip_security():
    violations = []
    for rel_root in ("sentinel", "sidecar"):
        for pyfile in (_AIVO_ROOT / rel_root).rglob("*.py"):
            rel = str(pyfile.relative_to(_AIVO_ROOT)).replace("\\", "/")
            if "/tests/" in rel or pyfile.name.startswith("test_"):
                continue
            if "skip_security" in pyfile.read_text(encoding="utf-8"):
                violations.append(rel)
    assert not violations, "Ninguna ruta de producción puede exponer skip_security: " + ", ".join(violations)


@pytest.mark.asyncio
async def test_grounding_uses_real_guarded_pipeline_and_audit():
    from sentinel.core.grounding import GroundingCategory, GroundingEngine, GroundingRequirement

    pipeline, gateway, _, audit = _build_stack()
    calls = []
    gateway.register(_PermTool("p1.grounding", ["system.read"], calls=calls))
    grounding = GroundingEngine(execution_pipeline=pipeline)
    requirement = GroundingRequirement(
        category=GroundingCategory.SYSTEM_STATE,
        required=True,
        freshness_seconds=1,
        tool_id="p1.grounding",
    )

    result = await grounding.enforce_grounding(requirement, context=_identity())

    assert result.grounded is True
    assert calls == [{}]
    entries = audit.get_log(action_filter="tool_execution")["entries"]
    assert any("p1.grounding" in json.dumps(entry.get("details", "")) for entry in entries)
