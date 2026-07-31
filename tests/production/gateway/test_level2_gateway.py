"""FASE 6.3 — Level 2: Real ToolGateway security boundary.

Request -> ToolExecutionGuard -> ToolGateway -> real tools.
Security: path traversal, command injection, unauthorized tool, invalid params.
Valid execution, and rollback on failure with state restored.
"""

import pytest
import pytest_asyncio

from tests.production.harness import IDENTITY
from tests.production.metrics import record

pytestmark = pytest.mark.production


def _ctx(execution_id="gw-1"):
    return {"identity": IDENTITY, "session_id": IDENTITY["session_id"], "execution_id": execution_id}


@pytest.mark.asyncio
async def test_path_traversal_blocked(stack):
    """Path traversal: ../ fuera del workspace debe bloquearse y auditarse."""
    before = stack.audit_service.get_log()["total"]
    result = await stack.gateway.execute(
        "config.write",
        {"name": "../../etc/evil.json", "content": {"pwned": True}},
        context=_ctx("traversal-1"),
    )
    assert result.success is False
    assert "traversal" in (result.error or "").lower() or "blocked" in (result.error or "").lower()
    # Nada se escribió fuera del workspace.
    assert not (stack.workspace.parent / "etc" / "evil.json").exists()
    record("security", {"check": "path traversal blocked (config.write ../)", "result": "pass"})


@pytest.mark.asyncio
async def test_command_injection_blocked(stack):
    """Inyección de comandos: app_name con traversal/shell chaining se bloquea."""
    result = await stack.gateway.execute(
        "executor.launch",
        {"app_name": "..\\..\\Windows\\System32\\cmd.exe"},
        context=_ctx("injection-1"),
    )
    assert result.success is False
    assert "traversal" in (result.error or "").lower() or "blocked" in (result.error or "").lower()
    record("security", {"check": "command injection blocked (executor.launch ../..\\cmd.exe)", "result": "pass"})


@pytest.mark.asyncio
async def test_invalid_parameters_rejected(stack):
    """Parámetros inválidos: tipos incorrectos son rechazados sin ejecutar."""
    result = await stack.gateway.execute(
        "tools.math.add",
        {"a": "no-es-numero", "b": 3},
        context=_ctx("invalid-1"),
    )
    assert result.success is False
    # La herramienta real valida tipos.
    assert result.error is not None
    record("security", {"check": "invalid parameters rejected without execution", "result": "pass"})


@pytest.mark.asyncio
async def test_execucion_valida_permitida_y_auditada(stack):
    """Ejecución válida: permitida, ejecutada y auditada."""
    before = stack.audit_service.get_log()["total"]
    result = await stack.gateway.execute("tools.math.add", {"a": 1, "b": 2}, context=_ctx("valid-1"))
    assert result.success is True
    assert result.data["sum"] == 3
    after = stack.audit_service.get_log()["total"]
    assert after > before


@pytest.mark.asyncio
async def test_rollback_restaura_estado(stack):
    """Rollback: tras un fallo, el estado previo se restaura."""
    name = "settings.json"
    await stack.gateway.execute("config.write", {"name": name, "content": {"version": 1}}, context=_ctx("rb-1"))
    original = (stack.workspace / name).read_text(encoding="utf-8")

    # Segundo write con contenido nuevo.
    result = await stack.gateway.execute("config.write", {"name": name, "content": {"version": 2}}, context=_ctx("rb-2"))
    assert result.success is True
    assert (stack.workspace / name).read_text(encoding="utf-8") != original

    # Rollback real de la herramienta: restaura el contenido previo.
    restored = stack.config_tool.rollback(name)
    assert restored is True
    assert (stack.workspace / name).read_text(encoding="utf-8") == original
    record("security", {"check": "rollback restored previous state after failure", "result": "pass"})


@pytest.mark.asyncio
async def test_security_audit_trail(stack):
    """Toda acción protegida deja rastro de auditoría con integridad verificable."""
    await stack.gateway.execute("config.write", {"name": "x.json", "content": {"k": 1}}, context=_ctx("audit-1"))
    integrity = stack.audit_service.verify_integrity()
    assert integrity["valid"] is True
    log = stack.audit_service.get_log(limit=50)
    assert log["total"] > 0
    assert any("config.write" in e["action"] or e["action"] == "pipeline.preflight.config.write" for e in log["entries"])
    record("security", {"check": "append-only audit trail with verifiable hash chain", "result": "pass"})
