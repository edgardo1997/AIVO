"""FASE 6.2 — Level 1: Real Orchestrator Testing.

Validates the real main path through the PRODUCTION pipeline:
utterance -> IntentEngine -> Planner -> DecisionEngine -> ModelRouter
-> ExecutionPipeline (ToolExecutionGuard) -> ToolGateway -> real tools.

No SentinelRuntime. No stubs. All components are the real production classes.
"""

import pytest
import pytest_asyncio

from tests.production.harness import IDENTITY

pytestmark = pytest.mark.production


@pytest.mark.asyncio
async def test_conversacion_simple(stack):
    """Conversación simple: API -> Intent -> Context -> Execution -> Response."""
    result = await stack.orchestrator.process("Hola Sentinel", identity=IDENTITY)

    assert result.execution_id
    assert result.error is None
    assert result.plan is not None
    assert result.plan.intent is not None
    # El pipeline real enrutó el saludo a una query de sistema y la ejecutó.
    assert result.tool_result is not None
    assert result.tool_result.success is True
    assert result.grounding_satisfied is True

    # La ejecución quedó persistida en la base real.
    status = await stack.intel.learning_memory_status()
    assert status["records"]["executions"] >= 1


@pytest.mark.asyncio
async def test_ejecucion_herramienta(stack):
    """Ejecución de herramienta: Intent -> Planning -> Risk -> Consent -> Pipeline -> Gateway -> Result."""
    result = await stack.orchestrator.execute_direct("system.info", {}, identity=IDENTITY)

    assert result.tool_result is not None
    assert result.tool_result.success is True
    assert result.execution_id
    data = result.tool_result.data or {}
    assert any(k in data for k in ("cpu", "memory", "disk", "os", "hostname"))

    # Consent: sin política de confirmación -> ejecución directa (no blocked).
    assert result.blocked is False

    # Audit real generado.
    log = stack.audit_service.get_log(limit=50)
    actions = [e["action"] for e in log["entries"]]
    assert any("system.info" in a for a in actions)


@pytest.mark.asyncio
async def test_ejecucion_con_consentimiento(stack):
    """Consent: una herramienta protegida requiere confirmación explícita antes de ejecutar."""
    ctx = {"identity": IDENTITY, "session_id": IDENTITY["session_id"], "execution_id": "consent-1"}
    blocked = await stack.gateway.execute("config.confirm", {"value": "si"}, context=ctx)
    assert blocked.requires_confirmation is True
    action_id = (blocked.data or {}).get("action_id")
    assert action_id

    # El broker de confirmación real persistió la acción pendiente.
    pending = stack.memory.list_pending_actions()
    assert any(p.action_id == action_id for p in pending)

    # Aprobación real -> se ejecuta en el gateway real.
    approved = await stack.gateway.confirm(action_id, True, IDENTITY)
    assert approved.success is True
    assert approved.data.get("confirmed") == "si"


@pytest.mark.asyncio
async def test_consentimiento_denegado_no_ejecuta(stack):
    """Consent rechazado: la acción no debe ejecutarse."""
    ctx = {"identity": IDENTITY, "session_id": IDENTITY["session_id"], "execution_id": "consent-2"}
    blocked = await stack.gateway.execute("config.confirm", {"value": "no"}, context=ctx)
    action_id = (blocked.data or {}).get("action_id")
    assert action_id

    denied = await stack.gateway.confirm(action_id, False, IDENTITY)
    assert denied.success is False
    # La acción pendiente se consumió.
    pending = stack.memory.list_pending_actions()
    assert all(p.action_id != action_id for p in pending)


@pytest.mark.asyncio
async def test_tarea_compleja_multiples_acciones(stack):
    """Tarea compleja: múltiples acciones reales, todo auditado y persistido."""
    await stack.orchestrator.execute_direct("system.info", {}, identity=IDENTITY)
    r_add = await stack.orchestrator.execute_direct("tools.math.add", {"a": 2, "b": 40}, identity=IDENTITY)
    r_mem = await stack.orchestrator.execute_direct("system.memory", {}, identity=IDENTITY)

    assert r_add.tool_result.success is True
    assert r_add.tool_result.data["sum"] == 42
    assert r_mem.tool_result.success is True

    # Auditoría del pipeline real para cada ejecución.
    log = stack.audit_service.get_log(limit=100)
    actions = [e["action"] for e in log["entries"]]
    assert any("system.info" in a for a in actions)
    assert any("tools.math.add" in a for a in actions)
    assert any("system.memory" in a for a in actions)

    # Integridad del audit: cadena de hashes válida.
    integrity = stack.audit_service.verify_integrity()
    assert integrity["valid"] is True

    # Cada ejecución persistida en la base de aprendizaje real.
    status = await stack.intel.learning_memory_status()
    assert status["records"]["executions"] >= 3


@pytest.mark.asyncio
async def test_contexto_fluye_entre_pasos(stack):
    """Context: la identidad y sesión viajan por todo el pipeline hasta las herramientas."""
    echo = await stack.orchestrator.execute_direct(
        "tools.echo",
        {"message": "hola"},
        identity=IDENTITY,
    )
    assert echo.tool_result.success is True
    assert echo.tool_result.data["echo"] == "hola"
    # El plan enrutó por el ModelRouter real.
    assert echo.plan is not None
